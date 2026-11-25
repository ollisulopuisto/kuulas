from dataclasses import replace

import numpy as np
import pytest
from test_engine import Clock, FakeSession, MemoryStore, install_rig
from test_history import register

from kuulas import mixer
from kuulas.align_review import Review, SyncError
from kuulas.engine import Engine
from kuulas.model import Clip, Media, Project, Track
from kuulas.session import Session


def project():
    return Project(rate=48000, media=(Media('m','m',1,480000),), tracks=(
        Track('a','Anchor',clips=(Clip('a1','m',0,0,48000),)),
        Track('b','Guest',clips=(Clip('b1','m',48000,0,48000),
                                Clip('b2','m',144000,48000,48000)))))


def test_track_move_preserves_gap_and_sources_and_does_not_edit_snapshot():
    p = project()
    r = Review(p,['b','a'])
    r.move('b',4800)
    clips = r.preview().tracks[1].clips
    assert [c.start for c in clips] == [52800,148800]
    assert [c.offset for c in clips] == [0,48000]
    assert r.project == p
    assert r.anchor == 'a'


def test_piece_move_is_explicit_absolute_offset_and_rejects_collision_atomically():
    r = Review(project(),['a','b'])
    r.move('b',2400,'b2')
    assert r.offsets == {'a1':0,'b1':0,'b2':2400}
    with pytest.raises(SyncError):
        r.move('b',-100000,'b2')
    assert r.offsets['b2'] == 2400
    with pytest.raises(SyncError):
        r.move('a',100)


def test_stale_snapshot_and_noninteger_offsets_fail():
    r = Review(project(),['a','b'])
    with pytest.raises(SyncError):
        r.check(replace(project(),master_gain_db=-2))
    for value in [True, 1.0, float('nan'),48000*20000]:
        with pytest.raises(SyncError):
            r.move('b',value)


def test_reset_uses_server_suggestion_and_ignores_unmatched_rows():
    r = Review(project(),['a','b'])
    r.set_result({'snapshot':r.key,'tracks':[{'track':'b','status':'proposal','delta':.1}]})
    r.move('b',4800)
    r.reset()
    assert r.offsets['b1'] == r.offsets['b2'] == 4800


def test_session_lock_preview_and_apply_one_undo(tmp_path):
    s=Session(tmp_path/'s.kuulas')
    try:
        register(s.history, 'm', 480000)
        original = project()
        original = replace(original, tracks=(original.tracks[0],
            replace(original.tracks[1], gate=((48000,72000),))))
        s.history.commit('fixture',original)
        before=s.state
        r=s.sync_begin(['a','b'])
        s.sync_move(r['id'],'b',4800)
        assert s.state==before
        with pytest.raises(SyncError):
            s.edit('set_track',{'track_id':'b','name':'bad'})
        with pytest.raises(SyncError):
            s.undo()
        preview=s.sync_review_project(r['id'])
        s.sync_apply(r['id'])
        assert s.state==preview
        s.undo()
        assert s.state==before
    finally:
        s.close()


def test_sync_preview_audio_matches_the_exact_applied_timing(monkeypatch):

    install_rig(monkeypatch)
    p=project()
    store=MemoryStore({'m':np.linspace(-.2,.2,480000,dtype=np.float32)[None,:]})
    session=FakeSession(p,store)
    engine=Engine(session,background=False,clock=Clock())
    try:
        r=Review(p,['a','b'])
        r.move('b',4800)
        expected=r.preview()
        engine.set_listen_source(expected,{})
        engine.play(48000)
        np.testing.assert_allclose(engine._render(1024),
                                   mixer.mix(expected,store,48000,1024).T,atol=1e-6)
        assert session.state==p
        engine.stop()
        engine.clear_listen_source()
        assert engine.listening is False
    finally:
        engine.close()


def test_after_apply_status_expires_on_next_edit(tmp_path):
    s=Session(tmp_path/'s.kuulas')
    try:
        register(s.history,'m',480000)
        s.history.commit('fixture',project())
        rid=s.sync_begin(['a','b'])['id']
        s.sync_move(rid,'b',4800)
        s.sync_apply(rid)
        assert s.sync_applied_status()[0]['manual'] is True
        s.undo()
        assert s.sync_applied_status()==[]
    finally:
        s.close()


def test_legacy_gate_silences_the_same_source_after_move():
    p=project()
    guest=replace(p.tracks[1],gate=((48000,72000),))
    p=replace(p,tracks=(p.tracks[0],guest))
    r=Review(p,['a','b'])
    r.move('b',4800)
    preview=r.preview()
    assert preview.tracks[1].gate==()
    assert preview.tracks[1].clips[0].auto_silence==((0,24000),)
    assert r.project.tracks[1].gate==((48000,72000),)



def test_legacy_gate_preview_pcm_follows_moved_source(monkeypatch):
    install_rig(monkeypatch)
    p=project()
    p=replace(p,tracks=(p.tracks[0],replace(p.tracks[1],gate=((48000,72000),))))
    store=MemoryStore({'m':np.full((1,480000),.1,dtype=np.float32)})
    r=Review(p,['a','b'])
    r.move('b',4800)
    preview=r.preview()
    old=mixer.mix(p,store,48000,48000)
    new=mixer.mix(preview,store,52800,48000)
    np.testing.assert_allclose(new,old,atol=1e-6)
    assert np.max(np.abs(new[:,5000:15000]))==0
    engine=Engine(FakeSession(p,store),background=False,clock=Clock())
    try:
        engine.set_listen_source(preview,{})
        engine.play(52800+5000)
        np.testing.assert_allclose(engine._render(1024),new[:,5000:6024].T,atol=1e-6)
    finally:
        engine.close()


def two_sets():
    return Project(rate=48000, media=(Media('m','m',1,960000),), tracks=(
        Track('a','Anchor',clips=(Clip('a1','m',0,0,48000),
                                  Clip('a2','m',480000,480000,48000))),
        Track('b','Guest',clips=(Clip('b1','m',48000,0,48000),
                                Clip('b2','m',528000,480000,48000)))))


def test_a_review_can_be_limited_to_some_pieces():
    r = Review(two_sets(),['a','b'],['a1','b1'])
    assert r.clip_ids == frozenset({'a1','b1'})
    r.move('b',4800)
    assert r.offsets == {'a1':0,'a2':0,'b1':4800,'b2':0}
    assert [c.start for c in r.preview().tracks[1].clips] == [52800,528000]
    assert r.view()['clips'] == ['a1','b1']
    assert Review(two_sets(),['a','b']).view()['clips'] is None


def test_a_piece_outside_the_choice_cannot_be_moved():
    r = Review(two_sets(),['a','b'],['a1','b1'])
    with pytest.raises(SyncError):
        r.move('b',100,'b2')
    assert r.offsets['b2'] == 0


def test_every_track_needs_a_chosen_piece():
    for chosen in (['a1'],['a1','zz'],[]):
        with pytest.raises(SyncError):
            Review(two_sets(),['a','b'],chosen)


def test_a_suggestion_moves_only_the_chosen_pieces():
    r = Review(two_sets(),['a','b'],['a1','b1'])
    r.set_result({'snapshot':r.key,'tracks':[{'track':'b','status':'proposal','delta':.1}]})
    assert r.offsets == {'a1':0,'a2':0,'b1':4800,'b2':0}
