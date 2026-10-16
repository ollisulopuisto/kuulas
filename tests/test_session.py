"""Session: one open project (WP1). The only place History, MediaStore and ops meet."""

import json
import logging
import struct
import threading
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import messages, transcript
from kuulas import session as session_module
from kuulas.clock import FLICKS, flicks_to_frames
from kuulas.history import HistoryError
from kuulas.media import MediaError
from kuulas.ops import EditError
from kuulas.session import COMMANDS, Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


def wav(path: Path, seconds: float = 1.0, channels: int = 1, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    n = round(seconds * RATE)
    shape = (n,) if channels == 1 else (n, channels)
    sf.write(path, (rng.standard_normal(shape) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    return path


def burst_wav(path: Path, talk: list[tuple[float, float]], seconds: float,
              seed: int) -> Path:
    """Noise where this speaker talks, near silence elsewhere: auto-silence has
    something to decide."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(round(seconds * RATE)) * 0.0005
    for a, b in talk:
        lo, hi = round(a * RATE), round(b * RATE)
        x[lo:hi] = rng.standard_normal(hi - lo) * 0.2
    sf.write(path, x.astype(np.float32), RATE, subtype="PCM_16")
    return path


def add_bext(path: Path, time_reference: int) -> None:
    """Insert a minimal BWF ``bext`` chunk with the given TimeReference."""
    data = path.read_bytes()
    bext = bytearray(602)
    struct.pack_into("<Q", bext, 338, time_reference)
    chunk = b"bext" + struct.pack("<I", len(bext)) + bytes(bext)
    body = data[12:] + chunk
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body)


def words(*spans: tuple[str, float, float]) -> list[dict]:
    return [{"w": w, "s": round(s * FLICKS), "e": round(e * FLICKS), "spk": ""}
            for w, s, e in spans]


def two_files(tmp_path):
    return [wav(tmp_path / "anna.wav", 3.0, seed=1),
            wav(tmp_path / "ville.wav", 3.0, seed=2)]


# -- the folder ------------------------------------------------------------------


def test_new_session_creates_the_folder_layout(tmp_path):
    folder = tmp_path / "Talk.kuulas"
    s = Session(folder)
    try:
        assert json.loads((folder / "manifest.json").read_text())["format"] == (
            "kuulas-project")
        for name in ("project.sqlite", "lock.json"):
            assert (folder / name).is_file()
        for name in ("media", "caches", "backups"):
            assert (folder / name).is_dir()
        assert s.state.rate == RATE
        assert s.state.tracks == ()
        assert not s.read_only
    finally:
        s.close()


def test_a_new_session_uses_the_requested_rate(tmp_path):
    s = Session(tmp_path / "Talk.kuulas", rate=44100)
    try:
        assert s.state.rate == 44100
    finally:
        s.close()


def test_an_existing_project_keeps_its_own_rate(tmp_path):
    Session(tmp_path / "Talk.kuulas", rate=44100).close()
    s = Session(tmp_path / "Talk.kuulas", rate=48000)
    try:
        assert s.state.rate == 44100
    finally:
        s.close()


def test_a_project_open_elsewhere_is_read_only(tmp_path):
    folder = tmp_path / "Talk.kuulas"
    Session(folder).close()
    (folder / "lock.json").write_text(json.dumps({
        "host": "some-other-computer", "pid": 1, "user": "x",
        "opened_utc": "2026-10-16T00:00:00Z",
        "heartbeat_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}))
    s = Session(folder)
    try:
        assert s.read_only
        with pytest.raises(HistoryError):
            s.edit("add_track", {"name": "A"})
    finally:
        s.close()


# -- edits and history -----------------------------------------------------------


def test_edit_commits_one_undo_step(session):
    session.edit("add_track", {"track_id": "A", "name": "Anna"})
    assert [t.id for t in session.state.tracks] == ["A"]
    assert len(session.history.nodes()) == 2  # the empty project, then the edit
    assert session.undo()
    assert session.state.tracks == ()
    assert not session.undo()


def test_edit_label_defaults_to_the_edit_name_and_the_op_is_kept(session):
    session.edit("add_track", {"track_id": "A"})
    session.edit("set_master", {"gain_db": -3.0}, label="quieter")
    nodes = session.history.nodes()
    assert [n["label"] for n in nodes[1:]] == ["add_track", "quieter"]
    assert nodes[2]["op"] == {"name": "set_master", "args": {"gain_db": -3.0}}


def test_unknown_edit_raises_edit_error_and_changes_nothing(session):
    with pytest.raises(EditError):
        session.edit("no_such_edit", {})
    assert len(session.history.nodes()) == 1


def test_a_failing_edit_leaves_no_step(session):
    with pytest.raises(EditError):
        session.edit("delete_track", {"track_id": "nope"})
    assert not session.history.can_undo


def test_redo_and_goto(session):
    session.edit("set_master", {"gain_db": -1.0})
    first = session.history.head
    session.edit("set_master", {"gain_db": -2.0})
    session.undo()
    assert session.state.master_gain_db == -1.0
    assert session.redo()
    assert session.state.master_gain_db == -2.0
    session.goto(first)
    assert session.state.master_gain_db == -1.0


def test_session_reopens_at_the_last_edit(tmp_path):
    folder = tmp_path / "Talk.kuulas"
    s = Session(folder)
    s.edit("add_track", {"track_id": "A", "name": "Anna"})
    s.edit("set_master", {"gain_db": -2.0})
    # No close(): the process dies here.
    again = Session(folder)
    try:
        assert [t.id for t in again.state.tracks] == ["A"]
        assert again.state.master_gain_db == -2.0
    finally:
        again.close()


def test_checkpoint_names_the_current_step(session):
    session.edit("set_master", {"gain_db": -1.0})
    session.checkpoint("sent to Ville")
    assert [c["name"] for c in session.history.checkpoints()] == ["sent to Ville"]


# -- solo and mute coalesce ------------------------------------------------------


def three_tracks(session):
    for i in "ABC":
        session.edit("add_track", {"track_id": i, "name": i})


def test_clicking_solo_through_tracks_is_one_undo_step(session):
    three_tracks(session)
    steps = len(session.history.nodes())
    for i in "ABC":
        session.edit("solo", {"track_id": i})
    assert [t.id for t in session.state.tracks if t.solo] == ["C"]
    assert len(session.history.nodes()) == steps + 1
    session.undo()
    assert not any(t.solo for t in session.state.tracks)


def test_mute_clicks_coalesce_per_track(session):
    three_tracks(session)
    steps = len(session.history.nodes())
    session.edit("set_track", {"track_id": "A", "mute": True})
    session.edit("set_track", {"track_id": "A", "mute": False})
    assert len(session.history.nodes()) == steps + 1
    session.edit("set_track", {"track_id": "B", "mute": True})
    assert len(session.history.nodes()) == steps + 2


def test_other_track_changes_do_not_coalesce(session):
    three_tracks(session)
    steps = len(session.history.nodes())
    session.edit("set_track", {"track_id": "A", "gain_db": -1.0})
    session.edit("set_track", {"track_id": "A", "gain_db": -2.0})
    assert len(session.history.nodes()) == steps + 2


def test_an_explicit_coalesce_key_wins(session):
    session.edit("set_master", {"gain_db": -1.0}, coalesce="drag")
    session.edit("set_master", {"gain_db": -2.0}, coalesce="drag")
    assert len(session.history.nodes()) == 2


# -- import ----------------------------------------------------------------------


def test_import_makes_one_track_per_file_in_one_undo_step(session, tmp_path):
    session.import_media([str(p) for p in two_files(tmp_path)])
    p = session.state
    assert [t.name for t in p.tracks] == ["anna", "ville"]
    assert all(len(t.clips) == 1 and t.clips[0].start == 0 for t in p.tracks)
    assert len(p.media) == 2
    nodes = session.history.nodes()
    assert len(nodes) == 2
    assert nodes[1]["label"] == "Import 2 files"
    session.undo()
    assert session.state.tracks == ()


def test_the_import_label_is_translated(session, tmp_path):
    messages.set_language("fi")
    session.import_media([str(wav(tmp_path / "a.wav"))])
    assert session.history.nodes()[1]["label"] == "Tuonti: 1 tiedosto"


def test_import_classifies_mono_as_speech_and_stereo_as_music(session, tmp_path):
    mono = wav(tmp_path / "voice.wav", channels=1, seed=1)
    stereo = wav(tmp_path / "song.wav", channels=2, seed=2)
    session.import_media([str(mono), str(stereo)])
    kinds = {t.name: t.kind for t in session.state.tracks}
    assert kinds == {"voice": "speech", "song": "music"}


def test_reimporting_the_same_file_adds_no_media(session, tmp_path):
    src = wav(tmp_path / "a.wav")
    session.import_media([str(src)])
    again = tmp_path / "copy-of-a.wav"
    again.write_bytes(src.read_bytes())
    session.import_media([str(again)])
    assert len(session.state.media) == 1


def test_files_imported_together_form_one_sync_group(session, tmp_path):
    session.import_media([str(p) for p in two_files(tmp_path)])
    p = session.state
    assert len(p.sync_groups) == 1
    group = p.sync_groups[0]
    assert group.main == p.tracks[0].clips[0].media
    assert {m for m, _ in group.members} == {m.id for m in p.media}
    assert all(origin == 0 for _, origin in group.members)


def test_the_sync_group_is_undone_with_the_import(session, tmp_path):
    session.import_media([str(p) for p in two_files(tmp_path)])
    session.undo()
    assert session.state.sync_groups == ()
    session.redo()
    assert len(session.state.sync_groups) == 1


def test_bwf_time_references_place_clips_relative_to_the_earliest(session, tmp_path):
    early = wav(tmp_path / "early.wav", 3.0, seed=1)
    late = wav(tmp_path / "late.wav", 3.0, seed=2)
    add_bext(early, RATE * 36000)
    add_bext(late, RATE * 36000 + RATE // 2)  # half a second later
    # Late first: the order of the files must not decide who is "earliest".
    session.import_media([str(late), str(early)])
    p = session.state
    starts = {t.name: t.clips[0].start for t in p.tracks}
    assert starts == {"early": 0, "late": RATE // 2}
    group = p.sync_groups[0]
    main = p.tracks[0].clips[0].media  # the first file: late
    assert group.main == main
    origins = dict(group.members)
    early_id = p.tracks[1].clips[0].media
    assert flicks_to_frames(origins[early_id], RATE) == -RATE // 2
    assert origins[main] == 0


def test_a_single_imported_file_gets_no_sync_group(session, tmp_path):
    session.import_media([str(wav(tmp_path / "a.wav"))])
    assert session.state.sync_groups == ()


def test_the_same_file_twice_in_one_import_is_not_a_group(session, tmp_path):
    src = wav(tmp_path / "a.wav")
    session.import_media([str(src), str(src)])
    assert len(session.state.tracks) == 2
    assert session.state.sync_groups == ()


def test_import_without_a_track_per_file_lines_the_files_up_on_one_track(
        session, tmp_path):
    session.import_media([str(p) for p in two_files(tmp_path)], track_per_file=False)
    p = session.state
    assert len(p.tracks) == 1
    assert [c.start for c in p.tracks[0].clips] == [0, 3 * RATE]
    assert p.sync_groups == ()  # one after the other is not the same moment


def test_a_file_that_cannot_be_imported_changes_nothing(session, tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("not audio")
    with pytest.raises(MediaError):
        session.import_media([str(bad)])
    assert session.state.tracks == ()
    assert not session.history.can_undo


# -- transcripts -----------------------------------------------------------------


def test_set_transcript_is_undoable(session, tmp_path):
    session.import_media([str(wav(tmp_path / "a.wav", 3.0))])
    media_id = session.state.media[0].id
    session.set_transcript(media_id, words(("one", 0.0, 0.4)), "transcribed")
    assert session.transcripts()[media_id][0]["w"] == "one"
    session.set_transcript(media_id, words(("won", 0.0, 0.4)), "corrected")
    assert session.transcripts()[media_id][0]["w"] == "won"
    assert session.history.nodes()[-1]["label"] == "corrected"
    session.undo()
    assert session.transcripts()[media_id][0]["w"] == "one"
    session.undo()
    assert session.transcripts() == {}


def test_set_transcript_for_unknown_media_is_an_edit_error(session):
    with pytest.raises(EditError):
        session.set_transcript("m-nothing", words(("one", 0.0, 0.4)), "x")
    assert not session.history.can_undo


def test_timeline_words_follow_the_clips(session, tmp_path):
    session.import_media([str(wav(tmp_path / "a.wav", 3.0))])
    media_id = session.state.media[0].id
    session.set_transcript(media_id, words(("one", 0.5, 0.9)), "t")
    assert session.timeline_words()[0]["s"] == RATE // 2
    clip = session.state.tracks[0].clips[0]
    session.edit("move_clip", {"clip_id": clip.id, "start": RATE})
    assert session.timeline_words()[0]["s"] == RATE + RATE // 2


def spoken(session, tmp_path):
    """Two tracks of the same length with the same three words each."""
    session.import_media([str(p) for p in two_files(tmp_path)])
    for m in session.state.media:
        session.set_transcript(m.id, words(("one", 0.0, 0.4), ("two", 0.5, 0.9),
                                           ("three", 1.0, 1.4)), "t")


def test_cut_words_ripples_every_track(session, tmp_path):
    spoken(session, tmp_path)
    ws = session.timeline_words()
    index = next(i for i, w in enumerate(ws) if w["w"] == "two")
    a, b = transcript.cut_range(ws, [index])
    before = len(session.history.nodes())
    session.command("cut_words", {"indices": [index]})
    p = session.state
    for track in p.tracks:
        assert sum(c.length for c in track.clips) == 3 * RATE - (b - a)
        assert max(c.end for c in track.clips) == 3 * RATE - (b - a)
    assert len(session.history.nodes()) == before + 1
    assert session.history.nodes()[-1]["label"] == "cut “two”"
    # The words that were left moved up by the cut.
    assert [w["w"] for w in session.timeline_words() if w["track"] == p.tracks[0].id] == (
        ["one", "three"])


def test_cut_words_is_one_undo_step(session, tmp_path):
    spoken(session, tmp_path)
    before = session.state
    session.command("cut_words", {"indices": [2]})
    session.undo()
    assert session.state == before


def test_cut_words_needs_words(session, tmp_path):
    spoken(session, tmp_path)
    with pytest.raises(EditError):
        session.command("cut_words", {"indices": []})
    with pytest.raises(EditError):
        session.command("cut_words", {"indices": [999]})


# -- commands --------------------------------------------------------------------


def test_unknown_command_raises_edit_error(session):
    with pytest.raises(EditError) as err:
        session.command("no_such_command", {})
    assert err.value.key == "error.edit.unknown"


def test_the_command_table_is_the_plans(session):
    assert set(COMMANDS) == {"auto_silence", "automix", "cut_words", "relink",
                             "consolidate", "create_person", "edit_person",
                             "create_interview", "edit_interview",
                                 "set_media_person", "map_speakers", "import_nhsx"}


def talkers(session, tmp_path):
    a = burst_wav(tmp_path / "a.wav", [(0.5, 2.0), (4.0, 5.0)], 6.0, seed=1)
    b = burst_wav(tmp_path / "b.wav", [(2.5, 3.5)], 6.0, seed=2)
    session.import_media([str(a), str(b)])


def test_auto_silence_is_one_undo_step(session, tmp_path):
    talkers(session, tmp_path)
    before = session.state
    session.command("auto_silence", {})
    assert any(c.muted for t in session.state.tracks for c in t.clips)
    assert len(session.history.nodes()) == 3
    session.undo()
    assert session.state == before


def test_auto_silence_can_be_limited_to_some_tracks(session, tmp_path):
    talkers(session, tmp_path)
    first = session.state.tracks[0].id
    session.command("auto_silence", {"track_ids": [first]})
    muted = {t.id: any(c.muted for c in t.clips) for t in session.state.tracks}
    assert muted[first]
    assert not muted[session.state.tracks[1].id]


def test_automix_writes_automation_in_one_step(session, tmp_path):
    talkers(session, tmp_path)
    session.command("automix", {"depth_db": -12.0})
    assert any(t.automation for t in session.state.tracks)
    assert len(session.history.nodes()) == 3
    session.undo()
    assert not any(t.automation for t in session.state.tracks)


def test_relink_finds_a_moved_file_and_commits_nothing(session, tmp_path):
    src = wav(tmp_path / "a.wav")
    session.import_media([str(src)])
    moved = tmp_path / "elsewhere"
    moved.mkdir()
    src.rename(moved / "renamed.wav")
    assert session.store.missing()
    nodes = session.history.nodes()
    state = session.state
    session.command("relink", {"folder": str(moved)})
    assert session.store.missing() == []
    assert session.history.nodes() == nodes
    assert session.state == state


def test_consolidate_copies_linked_media_in_and_commits_nothing(session, tmp_path):
    src = wav(tmp_path / "a.wav")
    session.import_media([str(src)])
    media_id = session.state.media[0].id
    assert session.store.is_linked(media_id)
    nodes = session.history.nodes()
    session.command("consolidate", {})
    assert not session.store.is_linked(media_id)
    assert session.history.nodes() == nodes


# -- subscribers -----------------------------------------------------------------


def test_subscribers_see_every_change_including_undo(session, tmp_path):
    seen = []
    session.subscribe(seen.append)
    session.edit("add_track", {"track_id": "A"})
    session.edit("set_master", {"gain_db": -1.0})
    session.undo()
    session.redo()
    assert [bool(p.tracks) and p.master_gain_db for p in seen] == [0.0, -1.0, 0.0, -1.0]
    session.import_media([str(wav(tmp_path / "a.wav", 3.0))])
    assert len(seen) == 5
    session.set_transcript(session.state.media[0].id, words(("one", 0.0, 0.4)), "t")
    assert len(seen) == 6
    session.goto(session.history.nodes()[0]["id"])
    assert len(seen) == 7


def test_nothing_to_undo_tells_no_one(session):
    seen = []
    session.subscribe(seen.append)
    assert not session.undo()
    assert not session.redo()
    assert seen == []


def test_a_failed_edit_tells_no_one(session):
    seen = []
    session.subscribe(seen.append)
    with pytest.raises(EditError):
        session.edit("delete_track", {"track_id": "nope"})
    assert seen == []


def test_a_failing_subscriber_does_not_undo_the_edit_or_silence_the_others(session):
    seen = []

    def broken(_state):
        raise RuntimeError("engine fell over")
    session.subscribe(broken)
    session.subscribe(seen.append)
    session.edit("add_track", {"track_id": "A"})
    assert [t.id for t in session.state.tracks] == ["A"]
    assert len(seen) == 1


# -- threads ---------------------------------------------------------------------


def test_edits_from_several_threads_all_land(session):
    session.edit("add_track", {"track_id": "A"})
    errors = []

    def work(n):
        try:
            for i in range(5):
                session.edit("set_track", {"track_id": "A", "name": f"{n}-{i}"})
                session.edit("set_master", {"gain_db": float(n)})
        except Exception as e:  # noqa: BLE001 - collected, asserted empty below
            errors.append(e)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    # 1 for the track, then 6 threads x 5 x 2 edits, none merged or lost.
    assert len(session.history.nodes()) == 1 + 1 + 60


# -- memoized views (WP36) -------------------------------------------------------


def counting_timeline_words(monkeypatch):
    calls = []
    real = transcript.timeline_words

    def counting(p, transcripts):
        calls.append(1)
        return real(p, transcripts)

    monkeypatch.setattr(transcript, "timeline_words", counting)
    return calls


def test_timeline_words_are_computed_once_per_state_and_transcript(
        session, tmp_path, monkeypatch):
    session.import_media([str(wav(tmp_path / "a.wav", 3.0))])
    media_id = session.state.media[0].id
    session.set_transcript(media_id, words(("one", 0.5, 0.9)), "t")
    calls = counting_timeline_words(monkeypatch)
    first = session.timeline_words()
    assert session.timeline_words() == first
    assert len(calls) == 1
    clip = session.state.tracks[0].clips[0]
    session.edit("move_clip", {"clip_id": clip.id, "start": RATE})
    moved = session.timeline_words()
    assert moved[0]["s"] == RATE + RATE // 2
    assert len(calls) == 2
    session.undo()  # back to a state already seen: no recompute
    assert session.timeline_words() == first
    assert len(calls) == 2
    session.redo()
    assert session.timeline_words() == moved
    assert len(calls) == 2


def test_a_corrected_transcript_invalidates_the_words(session, tmp_path, monkeypatch):
    session.import_media([str(wav(tmp_path / "a.wav", 3.0))])
    media_id = session.state.media[0].id
    session.set_transcript(media_id, words(("one", 0.5, 0.9)), "t")
    calls = counting_timeline_words(monkeypatch)
    assert session.timeline_words()[0]["w"] == "one"
    session.set_transcript(media_id, words(("won", 0.5, 0.9)), "fix")
    assert session.timeline_words()[0]["w"] == "won"
    session.undo()
    assert session.timeline_words()[0]["w"] == "one"
    assert len(calls) == 2


def test_a_caller_cannot_poison_the_memo(session, tmp_path):
    session.import_media([str(wav(tmp_path / "a.wav", 3.0))])
    media_id = session.state.media[0].id
    session.set_transcript(media_id, words(("one", 0.5, 0.9)), "t")
    session.timeline_words().clear()
    assert len(session.timeline_words()) == 1


def test_sync_partners_are_memoized_and_follow_the_material(
        session, tmp_path, monkeypatch):
    session.import_media([str(p) for p in two_files(tmp_path)])
    a, b = (m.id for m in session.state.media)
    assert session.sync_partners() == {a: (b,), b: (a,)}
    calls = []
    real = session_module._sync_partners
    monkeypatch.setattr(session_module, "_sync_partners",
                        lambda groups: calls.append(1) or real(groups))
    session.sync_partners()
    session.sync_partners()
    assert calls == []  # already memoized before the patch
    session.undo()  # the import, and its sync group, are gone
    assert session.sync_partners() == {}
    assert len(calls) == 1
    session.redo()
    assert session.sync_partners() == {a: (b,), b: (a,)}
    assert len(calls) == 1  # seen before


def test_closing_a_session_logs_the_cache_hit_rates(tmp_path, caplog):
    s = Session(tmp_path / "Talk.kuulas")
    s.import_media([str(wav(tmp_path / "a.wav", 1.0))])
    s.timeline_words()
    s.timeline_words()
    with caplog.at_level(logging.INFO, logger="kuulas.memory"):
        s.close()
    assert any("%" in r.getMessage() for r in caplog.records)
