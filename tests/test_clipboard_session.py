"""The clipboard wired into the session and the API (WP46): copy, cut, paste."""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import messages, transcript
from kuulas.clipboard_store import ClipboardStore, default_path
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


def history_len(s):
    return len(s.history.nodes())


def entries(s=None):
    return ClipboardStore(default_path()).load().entries()


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


def test_a_range_copy_keeps_the_window_and_the_layout(session):
    a, b = ids(session.state)
    out = session.clipboard_copy(start=10_000, end=30_000, track_ids=[a.id, b.id])
    session.clipboard_paste(out["entry"]["id"], at=150_000, mode="overwrite")
    got = [c for c in clips(session.state) if c[2] == 150_000]
    assert [(n, off, ln) for n, _, _, off, ln in got] == [("a", 10_000, 20_000),
                                                         ("b", 10_000, 20_000)]


def test_a_range_copy_takes_the_group_along_like_a_cut(session):
    a, _ = ids(session.state)
    # No sync groups: group editing means every track, as for a time-shifting edit.
    alone = session.clipboard_copy(start=0, end=1000, track_ids=[a.id])["entry"]
    grouped = session.clipboard_copy(start=0, end=1000, track_ids=[a.id],
                                     group_editing=True)["entry"]
    assert (alone["slots"], grouped["slots"]) == (1, 2)


def test_insert_shifts_later_material_by_the_pasted_span(session):
    a, _ = ids(session.state)
    session.edit("add_clip", {"track_id": a.id, "media_id": a.clips[0].media,
                              "start": 100_000, "offset": 0, "length": 10_000})
    entry = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id])["entry"]
    session.clipboard_paste(entry["id"], at=50_000, mode="insert", group_editing=False)
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
    other = Session(tmp_path / "Two.kuulas")
    try:
        other.import_media([str(tmp_path / "same-as-a.wav"),
                            str(wav(tmp_path / "c.wav", 3))])
        before = clips(other.state)
        result = other.clipboard_paste(entry["id"], at=200_000, mode="overwrite")
        assert result["missing"] == [sha_b]
        assert result["placed"] == 1
        assert len(clips(other.state)) == len(before) + 1
        other.undo()
        assert clips(other.state) == before
    finally:
        other.close()


def test_nothing_placeable_commits_nothing(tmp_path, session):
    a, _ = ids(session.state)
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]
    sha = session.state.media_item(a.clips[0].media).sha256
    other = Session(tmp_path / "Two.kuulas")
    try:
        other.import_media([str(wav(tmp_path / "c.wav", 3))])
        nodes = history_len(other)
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
    assert entries() == ()


def test_cut_copies_then_removes_with_ripple_in_one_step(session):
    a, b = ids(session.state)
    nodes = history_len(session)
    out = session.clipboard_cut(start=10_000, end=30_000, track_ids=[a.id, b.id])
    assert out["clipboard"]["ok"] is True
    assert history_len(session) == nodes + 1
    assert [c[2:] for c in clips(session.state) if c[0] == "a"] == [
        (0, 0, 10_000), (10_000, 30_000, 66_000)]
    [kept] = entries()
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
    assert entries() == ()


def test_backspace_never_touches_the_clipboard(session):
    a, _ = ids(session.state)
    session.clipboard_copy(clip_ids=[a.clips[0].id])
    before = ClipboardStore(default_path()).path.read_text(encoding="utf-8")
    session.edit("mute_range", {"start": 0, "end": 1000, "track_ids": [a.id]})
    session.edit("set_clips", {"clip_ids": [a.clips[0].id], "muted": True})
    assert ClipboardStore(default_path()).path.read_text(encoding="utf-8") == before


def test_a_damaged_clipboard_file_lists_empty_and_copy_repairs_it(session):
    default_path().write_text("{oops", encoding="utf-8")
    assert session.clipboard_list() == []
    a, _ = ids(session.state)
    session.clipboard_copy(clip_ids=[a.clips[0].id])
    assert len(session.clipboard_list()) == 1


def test_the_history_is_shared_between_sessions_and_restarts(tmp_path, session):
    a, _ = ids(session.state)
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id], name="Anna")["entry"]
    other = Session(tmp_path / "Two.kuulas")
    try:
        [seen] = other.clipboard_list()
        assert seen["id"] == entry["id"]
        assert seen["name"] == "Anna"
        assert seen["missing_here"] == 1  # Two has none of that audio yet
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
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}

    def close(self):
        pass


@pytest.fixture
def client(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, _Engine(), language="en", ui_dir=ui)) as c:
        yield c


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


def test_insert_with_group_editing_ripples_the_whole_sync_group(session, tmp_path):
    a, _b, _c = grouped(session, tmp_path)
    entry = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id])["entry"]
    # Group-editing on: the partner b follows, so a and b stay aligned.
    session.clipboard_paste(entry["id"], at=50_000, mode="insert",
                            target_tracks={"0": a.id}, group_editing=True)
    got = starts(session.state)
    assert got["a"] == [0, 50_000, 70_000]
    assert got["b"] == [0, 70_000]  # shifted by the span, no pasted clip
    assert got["c"] == [0]  # outside the group: untouched
    assert len(session.state.tracks[1].clips) == 2


def test_insert_with_group_editing_off_ripples_only_the_target(session, tmp_path):
    a, _b, _ = grouped(session, tmp_path)
    entry = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id])["entry"]
    session.clipboard_paste(entry["id"], at=50_000, mode="insert",
                            target_tracks={"0": a.id}, group_editing=False)
    got = starts(session.state)
    assert got["a"] == [0, 50_000, 70_000]
    assert got["b"] == [0]


def test_a_target_outside_any_group_follows_expand_ranges_old_rule(session, tmp_path):
    _a, _b, c = grouped(session, tmp_path)
    entry = session.clipboard_copy(start=0, end=20_000, track_ids=[c.id])["entry"]
    session.clipboard_paste(entry["id"], at=50_000, mode="insert",
                            target_tracks={"0": c.id}, group_editing=True)
    got = starts(session.state)
    # expand_range says a track in no group takes every track along.
    assert got["c"] == [0, 50_000, 70_000]
    assert got["a"] == [0, 70_000] or got["a"] == [0, 50_000, 70_000]
    assert got["a"][-1] == 70_000
    assert got["b"][-1] == 70_000


def test_group_insert_shifts_the_partners_automation_and_gate_and_undoes_in_one_step(
        session, tmp_path):
    a, b, _ = grouped(session, tmp_path)
    session.edit("set_gate", {"track_id": b.id, "ranges": [[70_000, 80_000]]})
    entry = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id])["entry"]
    before, nodes = session.state, history_len(session)
    session.clipboard_paste(entry["id"], at=50_000, mode="insert",
                            target_tracks={"0": a.id})  # group editing defaults on
    assert session.state.tracks[1].gate == ((90_000, 100_000),)
    assert history_len(session) == nodes + 1
    session.undo()
    assert session.state == before


def test_nothing_ripples_when_everything_is_missing(tmp_path, session):
    a, _b = ids(session.state)
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]
    other = Session(tmp_path / "Two.kuulas")
    try:
        other.import_media([str(wav(tmp_path / "d.wav", 4)),
                            str(wav(tmp_path / "e.wav", 5))])
        before = other.state
        other.clipboard_paste(entry["id"], at=100, mode="insert", group_editing=True)
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
    before_entries, before_steps = len(entries()), history_len(session)
    session.clipboard_copy(start=start, end=end, track_ids=tracks, group_editing=False)
    assert history_len(session) == before_steps
    session.command("cut_words", {"indices": [index]})
    assert len(entries()) == before_entries + 1
    assert history_len(session) == before_steps + 1


def test_insert_on_every_track_moves_markers_and_a_partial_insert_does_not(session):
    a, b = ids(session.state)
    session.edit("add_marker", {"marker_id": "m", "name": "After", "start": 90_000})
    session.edit("add_marker", {"marker_id": "r", "name": "Span", "start": 10_000,
                                "end": 60_000, "kind": "region"})
    one = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id])["entry"]
    session.clipboard_paste(one["id"], at=50_000, mode="insert", group_editing=False)
    assert [(m.start, m.end) for m in session.state.markers] == [
        (10_000, 60_000), (90_000, None)]  # only track a rippled
    both = session.clipboard_copy(start=0, end=20_000, track_ids=[a.id, b.id])["entry"]
    session.clipboard_paste(both["id"], at=50_000, mode="insert", group_editing=False)
    assert [(m.start, m.end) for m in session.state.markers] == [
        (10_000, 80_000), (110_000, None)]


def test_lift_cut_copies_and_mutes_in_place_in_one_step(session):
    a, b = ids(session.state)
    nodes = history_len(session)
    out = session.clipboard_lift_cut(start=10_000, end=30_000, track_ids=[a.id, b.id])
    assert out["clipboard"]["ok"] is True
    assert history_len(session) == nodes + 1
    # The gap stays: nothing moved, the stretch is muted, not removed.
    after = session.state
    assert [(c.start, c.length, c.muted) for c in after.tracks[0].clips] == [
        (0, 10_000, False), (10_000, 20_000, True), (30_000, 66_000, False)]
    [kept] = entries()
    assert kept.id == out["clipboard"]["entry"]
    assert kept.span == (10_000, 30_000)
    label = session.history.nodes()[-1]["label"]
    assert label == messages.t("history.clipboard_lift_cut")
    session.undo()
    assert clips(session.state)[0][2:] == (0, 0, 96_000)
    assert not any(c.muted for t in session.state.tracks for c in t.clips)


def test_lift_cut_still_mutes_when_the_copy_fails(session, monkeypatch):
    def full(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(ClipboardStore, "update", full)
    a, _ = ids(session.state)
    out = session.clipboard_lift_cut(start=10_000, end=30_000, track_ids=[a.id])
    assert out["clipboard"]["ok"] is False
    assert any(c.muted for c in session.state.tracks[0].clips)


def test_api_lift_cut_goes_through_edit(client, session):
    a, _ = ids(session.state)
    out = client.post("/api/edit", json={
        "op": "clipboard_lift_cut", "label": "Lift",
        "args": {"start": 10_000, "end": 30_000, "track_ids": [a.id],
                 "group_editing": False}})
    assert out.status_code == 200
    assert out.json()["clipboard"]["ok"] is True
    assert len(entries()) == 1
