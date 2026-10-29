from contextlib import closing
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from test_server import FakeEngine, wav

from kuulas import ops
from kuulas.history import History, HistoryError
from kuulas.model import Clip, Media, Project, Track
from kuulas.part_versions import distinct_versions, snapshot
from kuulas.server import create_app
from kuulas.session import Session


def project(media='a', *, clips=None):
    return Project(media=tuple(Media(x, x, 1, 1000) for x in 'abc'), tracks=(
        Track('t', 'Voice', clips=clips or (Clip('clip', media, 0, 100, 100),)),
        Track('other', 'Other', clips=(Clip('otherclip', 'c', 0, 0, 200),)),
    ))


def test_three_takes_dedup_and_occurrences():
    states = [(str(i), project(m)) for i, m in enumerate('abaca')]
    versions = distinct_versions(states, 't', 20, 80, current='4')
    assert [v.last_node for v in versions] == ['4', '3', '1']
    assert versions[0].first_node == '0'
    assert versions[0].current
    assert versions[0].clips[0].offset == 120
    assert versions[0].clips[0].length == 60


def test_clip_identity_and_artificial_seams_do_not_create_versions():
    whole = project()
    split = ops.split_clip(whole, 'clip', 50, 'split')
    assert len(distinct_versions([('0', whole), ('1', split)], 't', 20, 80)) == 1


def test_crossing_clips_preserves_holes_and_source_offsets():
    p = project(clips=(Clip('one', 'a', 0, 100, 30), Clip('two', 'b', 50, 200, 50)))
    s = snapshot(p, 't', 20, 80)
    assert [(c.start, c.offset, c.length) for c in s] == [(0, 120, 10), (30, 200, 30)]


def test_restore_overwrites_only_selected_range_without_ripple():
    old = project('a')
    now = replace(project('b'), master_gain_db=-3)
    result = ops.restore_part(now, old, 't', 20, 80)
    assert [(c.start, c.offset, c.length, c.media) for c in result.track('t').clips] == [
        (0, 100, 20, 'b'), (20, 120, 60, 'a'), (80, 180, 20, 'b')]
    assert result.track('other') == now.track('other')
    assert result.master_gain_db == -3
    assert len({c.id for t in result.tracks for c in t.clips}) == 4


def test_empty_historical_range_can_restore_silence():
    old = replace(project(), tracks=(Track('t', 'Voice'),))
    result = ops.restore_part(project(), old, 't', 20, 80)
    assert [(c.start, c.end) for c in result.track('t').clips] == [(0, 20), (80, 100)]


@pytest.mark.parametrize(('start', 'end'), [(20, 20), (80, 20), (-1, 10)])
def test_bad_ranges_rejected(start, end):
    with pytest.raises(ops.EditError):
        snapshot(project(), 't', start, end)


def test_restore_gate_and_clip_processing_without_changing_other_audio():
    old = project(clips=(replace(project().track('t').clips[0], gain_db=-6,
                                envelope=((100, -2), (200, -4))),))
    old = ops.set_gate(old, 't', [(10, 40), (70, 90)])
    now = ops.set_gate(project('b'), 't', [(0, 30), (60, 100)])
    result = ops.restore_part(now, old, 't', 20, 80)
    assert result.track('t').gate == ((0, 40), (70, 100))
    middle = result.track('t').clips[1]
    assert middle.gain_db == -6
    assert middle.envelope == ((100, -2), (200, -4))


def test_session_lists_abandoned_branch_and_restore_is_one_new_undoable_step(tmp_path):
    with closing(Session(tmp_path / 'Versions.kuulas')) as session:
        for media in 'abc':
            session.history.db.execute(
                "insert into media(id, sha256, name, storage, channels, source_rate,"
                " source_frames, lossless, added_utc) values (?, ?, ?, 'working',"
                " 1, 48000, 1000, 1, '2026-10-29T00:00:00Z')", (media, media, media))
        session.history.commit('a', project('a'))
        a = session.history.head
        session.history.commit('b', project('b'))
        b = session.history.head
        session.history.undo()
        session.history.commit('c', replace(project('c'), master_gain_db=-7))
        c = session.history.head
        session.history.commit('a again', replace(project('a'), master_gain_db=-7))
        d = session.history.head
        rows = session.part_versions('t', 20, 80)
        assert {r['node'] for r in rows} == {b, c, d}
        latest = next(r for r in rows if r['node'] == d)
        assert latest['current']
        revisited = next(r for r in rows if r['first_node'] == a)
        assert revisited['first_node'] == a
        assert revisited['node'] == d
        assert revisited['first_created'] == session.history._node(a)['created_utc']
        assert revisited['created'] == session.history._node(d)['created_utc']
        before = session.state
        session.restore_part(a, 't', 20, 80, expected_head=d)
        assert len(session.history.nodes()) == 6
        assert session.history.head != a
        assert session.state.master_gain_db == -7
        assert session.state.track('t').clips[1].media == 'a'
        session.history.undo()
        assert session.state == before
        with pytest.raises(ops.EditError):
            session.restore_part(a, 't', 20, 80, expected_head='stale')
        assert session.state == before


def test_http_list_preview_and_restore(tmp_path):

    with closing(Session(tmp_path / 'Http.kuulas')) as session:
        session.import_media([str(wav(tmp_path / 'voice.wav'))])
        original = session.state
        track = original.tracks[0]
        first = session.history.head
        session.history.commit(
            'mute', ops.set_clips(original, [track.clips[0].id], muted=True))
        head = session.history.head
        engine = FakeEngine()
        def play_preview(project, **kw):
            engine.calls.append(('preview', project))
        engine.play_preview = play_preview
        client = TestClient(create_app(session, engine))
        query = {'track_id': track.id, 'start': 100, 'end': 1000}
        response = client.get('/api/part-versions', params=query)
        assert response.status_code == 200
        assert len(response.json()['versions']) == 2
        body = {**query, 'node': first, 'expected_head': head}
        assert client.post('/api/part-versions/preview', json=body).status_code == 200
        assert session.history.head == head
        assert engine.calls[-1][0] == 'preview'
        assert engine.calls[-1][1].tracks[0].clips[0].start == 0
        assert client.post('/api/part-versions/restore', json=body).status_code == 200
        assert session.history.head != head
        assert client.post('/api/part-versions/restore', json=body).status_code == 400


def test_processing_changes_remain_distinct_and_missing_track_is_not_silence():
    p = project()
    changed = replace(p, tracks=(replace(p.tracks[0], clips=(
        replace(p.tracks[0].clips[0], fade_in=40, auto_silence=((120, 130),)),
    )),))
    versions = distinct_versions([('0', Project()), ('1', p), ('2', changed)],
                                 't', 0, 100)
    assert len(versions) == 2
    assert versions[0].clips[0].fade_in == 40
    assert versions[0].clips[0].auto_silence == ((120, 130),)


def test_restore_missing_media_fails_without_changing_project():
    now = replace(project('b'), media=tuple(m for m in project().media if m.id != 'a'))
    before = now.to_dict()
    with pytest.raises(ops.EditError, match=r'not exist|not found|media|Media'):
        ops.restore_part(now, project('a'), 't', 20, 80)
    assert now.to_dict() == before


def test_history_project_at_cannot_read_another_edits_node(tmp_path):
    history = History(tmp_path / 'history.sqlite')
    try:
        initial = history.head
        other = history.create_edit('Other')
        with closing(History(history.path, edit=other)) as second, \
                pytest.raises(HistoryError):
            second.project_at(initial)
    finally:
        history.close()
