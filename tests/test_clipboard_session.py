"""The clipboard wired into the session and the API (WP46): copy, cut, paste."""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import messages, transcript
from kuulas.clipboard_store import ClipboardStore
from kuulas.ops import EditError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


def wav(path: Path, seed: int, seconds: float = 2.0) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32),
             RATE, subtype="PCM_16")
    return path


@pytest.fixture
def files(tmp_path):
    return wav(tmp_path / "a.wav", 1), wav(tmp_path / "b.wav", 2)


@pytest.fixture
def session(tmp_path, files):
    s = Session(tmp_path / "One.kuulas")
    s.import_media([str(f) for f in files])
    yield s
    s.close()


def clips(project):
    """Every clip as (track name, media sha, start, offset, length), sorted."""
    sha = {m.id: m.sha256 for m in project.media}
    return sorted(((t.name, sha[c.media][:6], c.start, c.offset, c.length)
                   for t in project.tracks for c in t.clips),
                  key=lambda c: (c[0], c[2], c[1]))


def ids(project):
    a, b = project.tracks
    return a, b


def hand_over(source, target, entry_id):
    """Put one of ``source``'s entries on ``target``'s own clipboard, as adopting it
    does (the clipboard is per project since WP65)."""
    found = source.clipboard.load().get(entry_id)
    target.clipboard.update(lambda h: h.add(found))


def history_len(s):
    return len(s.history.nodes())


def entries(s):
    """The entries of the project's own clipboard (WP65)."""
    return s.clipboard.load().entries()


def test_copy_then_paste_on_the_same_tracks_reproduces_the_clips(session):
    a, b = ids(session.state)
    before = clips(session.state)
    out = session.clipboard_copy(clip_ids=[a.clips[0].id, b.clips[0].id])
    assert out["entry"]["clips"] == 2
    assert session.state == session.history.state  # copy changes nothing
    assert clips(session.state) == before
    result = session.clipboard_paste(out["entry"]["id"], at=200_000, mode="overwrite")
    assert result["placed"] == 2
    assert result["missing"] == []
    pasted = [c for c in clips(session.state) if c[2] == 200_000]
    assert sorted((n, s, off, ln) for n, s, _, off, ln in pasted) == [
        ("a", before[0][1], 0, 96_000), ("b", before[1][1], 0, 96_000)]


def test_copying_a_muted_clip_pastes_an_unmuted_copy(session):
    a, _ = ids(session.state)
    original = a.clips[0]
    session.edit("set_clips", {"clip_ids": [original.id], "muted": True})

    copied = session.clipboard_copy(clip_ids=[original.id])["entry"]["id"]
    session.clipboard_paste(copied, at=200_000, mode="overwrite")

    clips = session.state.tracks[0].clips
    assert next(c for c in clips if c.id == original.id).muted is True
    assert next(c for c in clips if c.start == 200_000).muted is False


def test_cutting_a_muted_clip_preserves_its_mute_when_pasted(session):
    a, _ = ids(session.state)
    original = a.clips[0]
    session.edit("set_clips", {"clip_ids": [original.id], "muted": True})

    cut = session.clipboard_cut(start=0, end=96_000, track_ids=[a.id])
    session.clipboard_paste(cut["clipboard"]["entry"], at=200_000, mode="overwrite")

    pasted = next(c for c in session.state.tracks[0].clips if c.start == 200_000)
    assert pasted.muted is True


def test_a_range_copy_keeps_the_window_and_the_layout(session):
    a, b = ids(session.state)
    out = session.clipboard_copy(start=10_000, end=30_000, track_ids=[a.id, b.id])
    session.clipboard_paste(out["entry"]["id"], at=150_000, mode="overwrite")
    got = [c for c in clips(session.state) if c[2] == 150_000]
    assert [(n, off, ln) for n, _, _, off, ln in got] == [("a", 10_000, 20_000),
                                                         ("b", 10_000, 20_000)]


def test_a_range_copy_without_tracks_takes_every_track(session):
    a, _ = ids(session.state)
    one = session.clipboard_copy(start=0, end=1000, track_ids=[a.id])["entry"]
    everything = session.clipboard_copy(start=0, end=1000)["entry"]
    assert (one["slots"], everything["slots"]) == (1, 2)


def test_insert_shifts_later_material_by_the_pasted_span(session):
    a, _ = ids(session.state)
    session.edit("add_clip", {"track_id": a.id, "media_id": a.clips[0].media,
                              "start": 100_000, "offset": 0, "length": 10_000})
    entry = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id])["entry"]
    session.clipboard_paste(entry["id"], at=50_000, mode="insert")
    on_a = [c[2:] for c in clips(session.state) if c[0] == "a"]
    assert on_a == [(0, 0, 50_000),            # the clip, cut at the paste point
                    (50_000, 0, 20_000),       # the pasted copy
                    (70_000, 50_000, 46_000),  # the rest of the clip, moved by 20 000
                    (120_000, 0, 10_000)]      # the later clip, moved by 20 000
    on_b = [c[2:] for c in clips(session.state) if c[0] == "b"]
    assert on_b == [(0, 0, 96_000)]  # group editing off: only the target ripples


def test_insert_also_moves_the_target_tracks_automation_and_gate(session):
    a, _ = ids(session.state)
    session.edit("set_track_automation",
                 {"track_id": a.id, "points": [[0, 0.0], [60_000, -6.0]]})
    session.edit("set_gate", {"track_id": a.id, "ranges": [[70_000, 80_000]]})
    entry = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id])["entry"]
    session.clipboard_paste(entry["id"], at=50_000, mode="insert")
    track = session.state.tracks[0]
    assert track.gate == ((90_000, 100_000),)
    assert (80_000, -6.0) in track.automation


def test_overwrite_replaces_the_covered_stretch_and_moves_nothing(session):
    a, _ = ids(session.state)
    src = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id])["entry"]
    session.clipboard_paste(src["id"], at=50_000, mode="overwrite")
    on_a = [c[2:] for c in clips(session.state) if c[0] == "a"]
    assert on_a == [(0, 0, 50_000), (50_000, 0, 20_000), (70_000, 70_000, 26_000)]


def test_paste_on_other_tracks_follows_the_mapping(session):
    a, b = ids(session.state)
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]
    # JSON object keys are strings: the API must accept "0".
    session.clipboard_paste(entry["id"], at=120_000, mode="overwrite",
                            target_tracks={"0": b.id})
    assert [c[2:] for c in clips(session.state) if c[0] == "b"] == [
        (0, 0, 96_000), (120_000, 0, 96_000)]


def test_one_paste_is_one_undo_step(session):
    a, b = ids(session.state)
    session.edit("add_clip", {"track_id": a.id, "media_id": a.clips[0].media,
                              "start": 100_000, "offset": 0, "length": 10_000})
    entry = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id, b.id])["entry"]
    before = session.state
    for mode in ("insert", "overwrite"):
        nodes = history_len(session)
        session.clipboard_paste(entry["id"], at=50_000, mode=mode)
        assert history_len(session) == nodes + 1
        assert session.state != before
        session.undo()
        assert session.state == before


def test_media_the_project_lacks_are_reported_not_raised(tmp_path, files, session):
    a, b = ids(session.state)
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id, b.clips[0].id])["entry"]
    sha_b = session.state.media_item(b.clips[0].media).sha256
    # Another project, which has a's recording (a copy under another name)
    # but not b's (it has c instead, so two tracks).
    shutil.copy(files[0], tmp_path / "same-as-a.wav")
    files[1].unlink()  # b's recording is gone from disk, so it cannot be linked
    other = Session(tmp_path / "Two.kuulas")
    try:
        other.import_media([str(tmp_path / "same-as-a.wav"),
                            str(wav(tmp_path / "c.wav", 3))])
        before = clips(other.state)
        hand_over(session, other, entry["id"])
        result = other.clipboard_paste(entry["id"], at=200_000, mode="overwrite")
        assert result["missing"] == [sha_b]
        assert result["placed"] == 1
        assert len(clips(other.state)) == len(before) + 1
        other.undo()
        assert clips(other.state) == before
    finally:
        other.close()


def test_nothing_placeable_commits_nothing(tmp_path, session, files):
    a, _ = ids(session.state)
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]
    files[0].unlink()  # gone from disk, so it cannot be linked either
    sha = session.state.media_item(a.clips[0].media).sha256
    other = Session(tmp_path / "Two.kuulas")
    try:
        other.import_media([str(wav(tmp_path / "c.wav", 3))])
        nodes = history_len(other)
        hand_over(session, other, entry["id"])
        result = other.clipboard_paste(entry["id"], at=0, mode="insert")
        assert result == {"placed": 0, "missing": [sha], "entry": entry["id"]}
        assert history_len(other) == nodes
    finally:
        other.close()


def test_unknown_entry_and_mode_are_errors(session):
    with pytest.raises(EditError):
        session.clipboard_paste("nope", at=0)
    first = session.state.tracks[0].id
    entry = session.clipboard_copy(start=0, end=100, track_ids=[first])
    with pytest.raises(messages.KuulasError):
        session.clipboard_paste(entry["entry"]["id"], at=0, mode="sideways")


def test_copy_with_nothing_selected_is_an_error(session):
    with pytest.raises(EditError):
        session.clipboard_copy(clip_ids=[])
    assert entries(session) == ()


def test_cut_copies_then_removes_with_ripple_in_one_step(session):
    a, b = ids(session.state)
    nodes = history_len(session)
    out = session.clipboard_cut(start=10_000, end=30_000, track_ids=[a.id, b.id])
    assert out["clipboard"]["ok"] is True
    assert history_len(session) == nodes + 1
    assert [c[2:] for c in clips(session.state) if c[0] == "a"] == [
        (0, 0, 10_000), (10_000, 30_000, 66_000)]
    [kept] = entries(session)
    assert kept.id == out["clipboard"]["entry"]
    assert len(kept.refs) == 2
    assert kept.span == (10_000, 30_000)
    session.undo()
    assert clips(session.state)[0][2:] == (0, 0, 96_000)


def test_cut_still_cuts_when_the_copy_fails(session, monkeypatch, caplog):
    def full(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(ClipboardStore, "update", full)
    a, b = ids(session.state)
    out = session.clipboard_cut(start=10_000, end=30_000, track_ids=[a.id, b.id])
    assert out["clipboard"]["ok"] is False
    assert "disk full" in out["clipboard"]["error"]
    assert [c[2:] for c in clips(session.state) if c[0] == "a"] == [
        (0, 0, 10_000), (10_000, 30_000, 66_000)]
    assert any("disk full" in r.getMessage() for r in caplog.records)


def test_cut_of_nothing_copyable_still_cuts_and_says_so(session):
    # A gap past the audio: the ripple is valid, there is nothing to copy.
    a, _ = ids(session.state)
    out = session.clipboard_cut(start=500_000, end=600_000, track_ids=[a.id])
    assert out["clipboard"]["ok"] is False
    assert out["clipboard"]["error"]
    assert entries(session) == ()


def test_backspace_never_touches_the_clipboard(session):
    a, _ = ids(session.state)
    session.clipboard_copy(clip_ids=[a.clips[0].id])
    before = session.clipboard.path.read_text(encoding="utf-8")
    session.edit("mute_range", {"start": 0, "end": 1000, "track_ids": [a.id]})
    session.edit("set_clips", {"clip_ids": [a.clips[0].id], "muted": True})
    assert session.clipboard.path.read_text(encoding="utf-8") == before


def test_a_damaged_clipboard_file_lists_empty_and_copy_repairs_it(session):
    session.clipboard.path.write_text("{oops", encoding="utf-8")
    assert session.clipboard_list() == []
    a, _ = ids(session.state)
    session.clipboard_copy(clip_ids=[a.clips[0].id])
    assert len(session.clipboard_list()) == 1


def test_each_project_has_its_own_history(tmp_path, session):
    a, _ = ids(session.state)
    session.clipboard_copy(clip_ids=[a.clips[0].id], name="Anna")
    other = Session(tmp_path / "Two.kuulas")
    try:
        assert other.clipboard_list() == []  # WP65: not shared unless marked
    finally:
        other.close()


def test_pin_rename_delete(session):
    a, _ = ids(session.state)
    e1 = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]["id"]
    e2 = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]["id"]
    assert [e["id"] for e in session.clipboard_list()] == [e2, e1]  # newest first
    session.clipboard_pin(e1, True)
    session.clipboard_rename(e1, "  Intro  ")
    first = next(e for e in session.clipboard_list() if e["id"] == e1)
    assert first["pinned"] is True
    assert first["name"] == "Intro"
    session.clipboard_pin(e1, False)
    session.clipboard_delete(e2)
    assert [e["id"] for e in session.clipboard_list()] == [e1]
    for call in (lambda: session.clipboard_delete("zz"),
                 lambda: session.clipboard_rename("zz", "x"),
                 lambda: session.clipboard_pin("zz", True)):
        with pytest.raises(EditError):
            call()


def test_the_clipboard_file_is_not_read_or_written_under_the_session_lock(
        session, monkeypatch):
    a, b = ids(session.state)
    seen = []
    real_load, real_update = ClipboardStore.load, ClipboardStore.update

    def load(self):
        seen.append(("load", session.lock._is_owned()))
        return real_load(self)

    def update(self, change):
        seen.append(("update", session.lock._is_owned()))
        return real_update(self, change)

    monkeypatch.setattr(ClipboardStore, "load", load)
    monkeypatch.setattr(ClipboardStore, "update", update)
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]
    session.clipboard_paste(entry["id"], at=300_000)
    session.clipboard_cut(start=0, end=1000, track_ids=[a.id, b.id])
    session.clipboard_list()
    assert seen
    assert not any(owned for _, owned in seen)


# -- the API -----------------------------------------------------------------


class _Engine:
    def __init__(self):
        self.previews = []
        self.stopped_previews = 0

    def stop_preview(self):
        self.stopped_previews += 1

    def play_preview(self, project, until=None, limit=False):
        self.previews.append(project)

    def status(self):
        return {"playing": bool(self.previews), "position": 0, "until": None,
                "notices": [], "seq": 3 + len(self.previews),
                "preview": bool(self.previews)}

    def close(self):
        pass


@pytest.fixture
def engine():
    return _Engine()


@pytest.fixture
def client(session, tmp_path, engine):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, engine, language="en", ui_dir=ui)) as c:
        yield c


def test_api_preview_plays_a_temp_project_and_changes_nothing(client, session, engine):
    a, _ = ids(session.state)
    body = {"clip_ids": [a.clips[0].id]}
    entry = client.post("/api/clipboard/copy", json=body).json()["entry"]
    head, before = history_len(session), clips(session.state)
    r = client.post(f"/api/clipboard/{entry['id']}/preview")
    assert r.status_code == 200
    assert r.json()["started"] is True
    assert r.json()["missing"] == 0
    assert r.json()["attenuation_db"] <= 0.0
    # The engine's transport version once it plays: the page drops an older "ended".
    assert r.json()["seq"] == 4
    (temp,) = engine.previews
    shape = [(t.id, [c.start for c in t.clips]) for t in temp.tracks]
    assert shape == [(a.id, [0]), (ids(session.state)[1].id, [])]
    assert history_len(session) == head
    assert clips(session.state) == before


def test_api_stop_preview_ends_only_the_preview(client, engine):
    r = client.post("/api/clipboard/preview/stop")
    assert r.status_code == 200
    assert engine.stopped_previews == 1


def test_api_preview_of_an_unknown_entry_is_a_404(client, engine):
    assert client.post("/api/clipboard/nope/preview").status_code == 404
    assert engine.previews == []


def test_api_copy_list_pin_rename_delete(client, session):
    a, _ = ids(session.state)
    body = {"clip_ids": [a.clips[0].id], "name": "Anna"}
    r = client.post("/api/clipboard/copy", json=body)
    assert r.status_code == 200
    entry = r.json()["entry"]
    listed = client.get("/api/clipboard").json()["entries"]
    assert [e["id"] for e in listed] == [entry["id"]]
    assert listed[0]["name"] == "Anna"
    assert listed[0]["clips"] == 1
    pin = client.post(f"/api/clipboard/{entry['id']}/pin", json={"pinned": True})
    rename = client.post(f"/api/clipboard/{entry['id']}/rename", json={"name": "B"})
    assert (pin.status_code, rename.status_code) == (200, 200)
    listed = client.get("/api/clipboard").json()["entries"]
    assert listed[0]["pinned"] is True
    assert listed[0]["name"] == "B"
    assert client.delete(f"/api/clipboard/{entry['id']}").status_code == 200
    assert client.get("/api/clipboard").json()["entries"] == []
    assert client.delete(f"/api/clipboard/{entry['id']}").status_code == 404


def test_api_copy_with_nothing_is_a_400(client):
    assert client.post("/api/clipboard/copy", json={"clip_ids": []}).status_code == 400


def test_api_cut_and_paste_go_through_edit_and_undo_together(client, session):
    a, b = ids(session.state)
    cut = client.post("/api/edit", json={
        "op": "clipboard_cut", "label": "Cut",
        "args": {"start": 10_000, "end": 30_000, "track_ids": [a.id, b.id],
                 "group_editing": False}})
    assert cut.status_code == 200
    assert cut.json()["clipboard"]["ok"] is True
    entry_id = cut.json()["clipboard"]["entry"]
    paste = client.post("/api/edit", json={
        "op": "clipboard_paste", "label": "Paste",
        "args": {"entry_id": entry_id, "at": 0, "mode": "insert", "target_tracks": None}})
    assert paste.status_code == 200
    assert paste.json()["clipboard"] == {"placed": 2, "missing": [], "entry": entry_id}
    assert client.post("/api/undo").json()["project"]["tracks"][0]["clips"][0]["length"] \
        == 10_000  # the paste is undone, the cut is not
    assert client.post("/api/undo").json()["project"]["tracks"][0]["clips"][0]["length"] \
        == 96_000


def test_api_backspace_does_not_touch_the_clipboard(client, session):
    a, _ = ids(session.state)
    r = client.post("/api/edit", json={"op": "mute_range", "args": {
        "start": 0, "end": 1000, "track_ids": [a.id], "group_editing": True}})
    assert r.status_code == 200
    assert "clipboard" not in r.json()
    assert client.get("/api/clipboard").json()["entries"] == []


def test_api_paste_of_an_unknown_entry_is_a_404(client):
    r = client.post("/api/edit", json={"op": "clipboard_paste", "args": {
        "entry_id": "nope", "at": 0}})
    assert r.status_code == 404


def test_api_edit_still_reports_unknown_ops(client):
    r = client.post("/api/edit", json={"op": "nope", "args": {}})
    assert r.status_code == 400
    json.dumps(r.json())


def test_api_paste_that_the_tracks_rule_out_is_a_400(tmp_path, client, session):
    a, b = ids(session.state)
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id, b.clips[0].id])["entry"]
    # Mapping only one of the two source tracks.
    r = client.post("/api/edit", json={"op": "clipboard_paste", "args": {
        "entry_id": entry["id"], "at": 0, "target_tracks": {"0": a.id}}})
    assert r.status_code == 400


# -- insert keeps a sync group together (WP19a) ---------------------------------------


def starts(project):
    """track name -> clip starts."""
    return {t.name: [c.start for c in t.clips] for t in project.tracks}


def grouped(session, tmp_path):
    """Tracks a and b in one sync group, and c (another recording) outside any."""
    session.import_media([str(wav(tmp_path / "c.wav", 3))])
    a, b, c = session.state.tracks
    session.edit("mark_in_sync", {"clip_ids": [a.clips[0].id, b.clips[0].id],
                                  "main": a.clips[0].id, "group_id": "g"})
    return a, b, c


def test_insert_ripples_only_the_target_tracks_sync_is_not_a_scope(session, tmp_path):
    a, _b, _c = grouped(session, tmp_path)
    entry = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id])["entry"]
    session.clipboard_paste(entry["id"], at=50_000, mode="insert",
                            target_tracks={"0": a.id})
    got = starts(session.state)
    assert got["a"] == [0, 50_000, 70_000]
    assert got["b"] == [0]  # a sync partner does not follow (WP83)
    assert got["c"] == [0]


def test_insert_on_one_track_leaves_the_others_gate_and_undoes_in_one_step(
        session, tmp_path):
    a, b, _ = grouped(session, tmp_path)
    session.edit("set_gate", {"track_id": b.id, "ranges": [[70_000, 80_000]]})
    entry = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id])["entry"]
    before, nodes = session.state, history_len(session)
    session.clipboard_paste(entry["id"], at=50_000, mode="insert",
                            target_tracks={"0": a.id})
    assert session.state.tracks[1].gate == ((70_000, 80_000),)
    assert history_len(session) == nodes + 1
    session.undo()
    assert session.state == before


def test_nothing_ripples_when_everything_is_missing(tmp_path, session, files):
    a, _b = ids(session.state)
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]
    # The recordings are gone from disk too, so linking them cannot help (it can
    # when they are still there: see the tests on pasting into another project).
    for f in files:
        f.unlink()
    other = Session(tmp_path / "Two.kuulas")
    try:
        other.import_media([str(wav(tmp_path / "d.wav", 4)),
                            str(wav(tmp_path / "e.wav", 5))])
        before = other.state
        hand_over(session, other, entry["id"])
        other.clipboard_paste(entry["id"], at=100, mode="insert")
        assert other.state == before
    finally:
        other.close()


def test_copying_a_words_stretch_then_cut_words_is_one_entry_and_one_undo_step(session):
    """The transcript's X: copy the range on every track, then cut_words."""
    for m in session.state.media:
        session.set_transcript(m.id, [
            {"w": "one", "s": 0, "e": round(0.4 * 705_600_000), "spk": ""},
            {"w": "two", "s": round(0.5 * 705_600_000), "e": round(0.9 * 705_600_000),
             "spk": ""}], "t")
    words = session.timeline_words()
    index = next(i for i, w in enumerate(words) if w["w"] == "two")
    start, end = transcript.cut_range(words, [index])
    tracks = [t.id for t in session.state.tracks]
    before_entries, before_steps = len(entries(session)), history_len(session)
    session.clipboard_copy(start=start, end=end, track_ids=tracks)
    assert history_len(session) == before_steps
    session.command("cut_words", {"indices": [index]})
    assert len(entries(session)) == before_entries + 1
    assert history_len(session) == before_steps + 1


def test_insert_on_every_track_moves_markers_and_a_partial_insert_does_not(session):
    a, b = ids(session.state)
    session.edit("add_marker", {"marker_id": "m", "name": "After", "start": 90_000})
    session.edit("add_marker", {"marker_id": "r", "name": "Span", "start": 10_000,
                                "end": 60_000, "kind": "region"})
    one = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id])["entry"]
    session.clipboard_paste(one["id"], at=50_000, mode="insert")
    assert [(m.start, m.end) for m in session.state.markers] == [
        (10_000, 60_000), (90_000, None)]  # only track a rippled
    both = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id, b.id])["entry"]
    session.clipboard_paste(both["id"], at=50_000, mode="insert")
    assert [(m.start, m.end) for m in session.state.markers] == [
        (10_000, 80_000), (110_000, None)]


def test_lift_cut_copies_and_deletes_leaving_the_gap_in_one_step(session):
    a, b = ids(session.state)
    nodes = history_len(session)
    out = session.clipboard_lift_cut(start=10_000, end=30_000, track_ids=[a.id, b.id])
    assert out["clipboard"]["ok"] is True
    assert history_len(session) == nodes + 1
    # The gap stays: nothing moved, the stretch is REMOVED (owner 2026-10-19: not muted).
    after = session.state
    assert [(c.start, c.length, c.muted) for c in after.tracks[0].clips] == [
        (0, 10_000, False), (30_000, 66_000, False)]
    [kept] = entries(session)
    assert kept.id == out["clipboard"]["entry"]
    assert kept.span == (10_000, 30_000)
    label = session.history.nodes()[-1]["label"]
    assert label == messages.t("history.clipboard_lift_cut")
    session.undo()
    assert clips(session.state)[0][2:] == (0, 0, 96_000)
    assert not any(c.muted for t in session.state.tracks for c in t.clips)


def test_lift_cut_still_deletes_when_the_copy_fails(session, monkeypatch):
    def full(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(ClipboardStore, "update", full)
    a, _ = ids(session.state)
    out = session.clipboard_lift_cut(start=10_000, end=30_000, track_ids=[a.id])
    assert out["clipboard"]["ok"] is False
    assert [(c.start, c.length) for c in session.state.tracks[0].clips] == [
        (0, 10_000), (30_000, 66_000)]
    assert not any(c.muted for c in session.state.tracks[0].clips)


def test_api_lift_cut_goes_through_edit(client, session):
    a, _ = ids(session.state)
    out = client.post("/api/edit", json={
        "op": "clipboard_lift_cut", "label": "Lift",
        "args": {"start": 10_000, "end": 30_000, "track_ids": [a.id],
                 "group_editing": False}})
    assert out.status_code == 200
    assert out.json()["clipboard"]["ok"] is True
    assert len(entries(session)) == 1


# -- pasting into another project: the media are linked on paste ----------------


@pytest.fixture
def other(tmp_path):
    s = Session(tmp_path / "Two.kuulas")
    s.import_media([str(wav(tmp_path / "d.wav", 4))])
    yield s
    s.close()


def test_pasting_into_another_project_links_the_recording_from_where_it_lives(
        session, other, files):
    a, _ = ids(session.state)
    sha = session.state.media[0].sha256
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]
    assert sha not in {m.sha256 for m in other.state.media}
    media_before = len(other.state.media)
    head = history_len(other)
    hand_over(session, other, entry["id"])
    result = other.clipboard_paste(entry["id"], at=0, mode="overwrite")
    assert result["placed"] == 1
    assert result["missing"] == []
    assert sha in {m.sha256 for m in other.state.media}
    assert len(other.state.media) == media_before + 1
    assert history_len(other) == head + 1  # the paste is the one undo step
    linked = next(m for m in other.state.media if m.sha256 == sha)
    assert other.store.is_linked(linked.id)  # linked in place, not copied
    assert Path(other.store.meta(linked.id)["linked_path"]) == files[0].resolve()
    placed = [c for t in other.state.tracks for c in t.clips if c.media == linked.id]
    assert [c.length for c in placed] == [a.clips[0].length]


def test_a_recording_that_has_gone_is_reported_missing_not_an_error(
        session, other, files):
    a, _ = ids(session.state)
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]
    files[0].unlink()
    before = other.state
    hand_over(session, other, entry["id"])
    result = other.clipboard_paste(entry["id"], at=0, mode="insert")
    assert result["placed"] == 0
    assert len(result["missing"]) == 1
    assert other.state == before


def test_a_file_changed_since_is_not_linked(session, other, files):
    a, _ = ids(session.state)
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]
    wav(files[0], 99)  # same name, different bytes
    hand_over(session, other, entry["id"])
    result = other.clipboard_paste(entry["id"], at=0, mode="insert")
    assert result["placed"] == 0
    assert len(result["missing"]) == 1
    assert len(other.state.media) == 1  # nothing foreign was linked


def test_the_list_shows_the_source_track_names_and_project(session):
    a, b = ids(session.state)
    session.clipboard_copy(clip_ids=[a.clips[0].id, b.clips[0].id])
    (view,) = session.clipboard_list()
    assert view["tracks"] == [a.name, b.name]
    assert view["source_name"] == "One"


def test_the_clipboard_can_be_put_in_another_order(session):
    a, _ = ids(session.state)
    e1 = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]["id"]
    e2 = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]["id"]
    e3 = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]["id"]
    assert [e["id"] for e in session.clipboard_list()] == [e3, e2, e1]
    session.clipboard_move(e1, before=e3)
    assert [e["id"] for e in session.clipboard_list()] == [e1, e3, e2]
    session.clipboard_move(e1, before=None)
    assert [e["id"] for e in session.clipboard_list()] == [e3, e2, e1]
    with pytest.raises(Exception, match=r"no|entry"):
        session.clipboard_move("nope", before=e3)


def test_api_moves_a_clipboard_entry(client, session):
    a, _ = ids(session.state)
    body = {"clip_ids": [a.clips[0].id]}
    first = client.post("/api/clipboard/copy", json=body).json()["entry"]["id"]
    second = client.post("/api/clipboard/copy", json=body).json()["entry"]["id"]
    r = client.post(f"/api/clipboard/{first}/move", json={"before": second})
    assert r.status_code == 200
    assert [e["id"] for e in r.json()["entries"]] == [first, second]
    r = client.post(f"/api/clipboard/{first}/move", json={"before": None})
    assert [e["id"] for e in r.json()["entries"]] == [second, first]


def test_the_cart_slots_are_given_and_the_view_shows_them(session):
    a, _ = ids(session.state)
    e1 = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]["id"]
    e2 = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]["id"]
    session.clipboard_cart(e1, 2)
    session.clipboard_cart(e2, 2)  # moves the number
    carts = {e["id"]: e["cart"] for e in session.clipboard_list()}
    assert carts == {e1: None, e2: 2}
    session.clipboard_cart(e2, None)
    assert all(e["cart"] is None for e in session.clipboard_list())


def test_a_bad_cart_slot_is_a_translated_error(session):
    a, _ = ids(session.state)
    e1 = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]["id"]
    with pytest.raises(EditError) as e:
        session.clipboard_cart(e1, 8)
    assert e.value.key == "error.clipboard.bad_slot"
    with pytest.raises(EditError):
        session.clipboard_cart("nope", 1)


def test_api_sets_a_cart_slot(client, session):
    a, _ = ids(session.state)
    body = {"clip_ids": [a.clips[0].id]}
    entry = client.post("/api/clipboard/copy", json=body).json()["entry"]
    r = client.post(f"/api/clipboard/{entry['id']}/cart", json={"slot": 5})
    assert r.status_code == 200
    assert [e["cart"] for e in r.json()["entries"]] == [5]
    r = client.post(f"/api/clipboard/{entry['id']}/cart", json={"slot": 11})
    assert r.status_code == 400


def test_a_whole_recording_can_be_copied_to_the_clipboard(session):
    a, _ = ids(session.state)
    media_id = a.clips[0].media
    result = session.material_copy(media_id)
    entry = result["entry"]
    assert entry["clips"] == 1
    assert entry["length"] == session.state.media_item(media_id).frames
    assert [e["id"] for e in session.clipboard_list()] == [entry["id"]]
    with pytest.raises(EditError):
        session.material_copy("no-such-media")


def test_api_material_lists_the_recordings_and_copies_one(client, session):
    a, _ = ids(session.state)
    media_id = a.clips[0].media
    rows = client.get("/api/material").json()["rows"]
    assert media_id in {r["id"] for r in rows}
    r = client.post(f"/api/material/{media_id}/copy")
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 1
    assert client.post("/api/material/nope/copy").status_code == 400
