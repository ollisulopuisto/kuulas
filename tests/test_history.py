import socket
import sqlite3
import uuid

import pytest

from kuulas import ops, transcript
from kuulas.history import History, HistoryError, edit_blob
from kuulas.model import Media, Project


def gain(h: History) -> float:
    return h.state.master_gain_db


def edit(h: History, db: float, key: str | None = None) -> None:
    h.commit(f"master {db}", ops.set_master(h.state, db), coalesce=key)


def test_new_history_starts_from_an_empty_project(tmp_path):
    h = History(tmp_path / "p.kuulas")
    assert h.state == Project()
    assert not h.can_undo


def test_every_edit_survives_a_crash(tmp_path):
    h = History(tmp_path / "p.kuulas")
    edit(h, -1.0)
    edit(h, -2.0)
    # No close(): the process dies here.
    again = History(tmp_path / "p.kuulas")
    assert gain(again) == -2.0
    again.undo()
    assert gain(again) == -1.0


def test_undo_then_new_edit_keeps_the_abandoned_branch(tmp_path):
    h = History(tmp_path / "p.kuulas")
    edit(h, -1.0)
    edit(h, -2.0)
    abandoned = h.head
    h.undo()
    edit(h, -3.0)
    assert gain(h) == -3.0
    # Nothing is lost: the undone edit is still a node we can go back to.
    h.goto(abandoned)
    assert gain(h) == -2.0


def test_redo_follows_the_most_recent_branch(tmp_path):
    h = History(tmp_path / "p.kuulas")
    edit(h, -1.0)
    edit(h, -2.0)
    h.undo()
    edit(h, -3.0)
    h.undo()
    h.redo()
    assert gain(h) == -3.0


def test_slider_drags_coalesce_into_one_undo_step(tmp_path):
    h = History(tmp_path / "p.kuulas")
    edit(h, -1.0)
    for db in (-2.0, -3.0, -4.0):
        edit(h, db, key="master")
    assert gain(h) == -4.0
    h.undo()
    assert gain(h) == -1.0


def test_coalescing_stops_after_an_undo(tmp_path):
    h = History(tmp_path / "p.kuulas")
    edit(h, -1.0, key="master")
    h.undo()
    h.redo()
    edit(h, -2.0, key="master")
    h.undo()
    assert gain(h) == -1.0


def test_transcripts_are_stored_once_not_per_step(tmp_path):
    h = History(tmp_path / "p.kuulas")
    words = [{"w": "moi", "s": 0, "e": 4800, "spk": "A"}]
    rev = h.add_transcript("m1", words)
    assert h.transcript(rev) == words
    edit(h, -1.0)
    db = sqlite3.connect(tmp_path / "p.kuulas")
    # v1 schema (docs/FORMAT.md): one revision row, its words stored once.
    assert db.execute("select count(*) from transcript_revs").fetchone()[0] == 1
    assert db.execute("select count(*) from blobs where kind='words'").fetchone()[0] == 1


def test_history_lists_nodes_with_labels(tmp_path):
    h = History(tmp_path / "p.kuulas")
    edit(h, -1.0)
    nodes = h.nodes()
    assert [n["label"] for n in nodes] == ["new project", "master -1.0"]
    assert nodes[1]["parent"] == nodes[0]["id"]


def test_identical_states_are_stored_once(tmp_path):
    h = History(tmp_path / "p.kuulas")
    for _ in range(3):
        edit(h, -1.0)
        edit(h, -2.0)
    for _ in range(4):
        h.undo()
        h.redo()
    db = sqlite3.connect(tmp_path / "p.kuulas")
    count = "select count(*) from blobs where kind='edit-state'"
    # The empty project, -1 dB and -2 dB: three states however many steps.
    assert db.execute(count).fetchone()[0] == 3
    assert db.execute("select count(*) from nodes").fetchone()[0] == 7


def test_step_ids_are_uuid7_and_record_author_and_machine(tmp_path):
    h = History(tmp_path / "p.kuulas", author="Ville")
    for db in (-1.0, -2.0, -3.0):
        edit(h, db)
    nodes = h.nodes()
    ids = [uuid.UUID(n["id"]) for n in nodes]
    assert all(u.version == 7 and u.variant == uuid.RFC_4122 for u in ids)
    # Time-ordered: sorting the ids gives the order the steps were made in.
    assert sorted(ids) == ids
    assert {n["author"] for n in nodes[1:]} == {"Ville"}
    assert {n["machine"] for n in nodes} == {socket.gethostname()}
    # The edit that made each step is kept as an audit trail.
    h.commit("master -4", ops.set_master(h.state, -4.0),
             op={"name": "set_master", "args": {"gain_db": -4.0}})
    assert h.nodes()[-1]["op"] == {"name": "set_master", "args": {"gain_db": -4.0}}


WORDS = [{"w": "hei", "s": 0, "e": 480, "spk": "A"}]
FIXED = [{"w": "Hei!", "s": 0, "e": 480, "spk": "A"}]
AGAIN = [{"w": "Hei.", "s": 0, "e": 480, "spk": "A"}]


def test_material_undo_moves_the_material_back(tmp_path):
    h = History(tmp_path / "p.kuulas")
    first = h.add_transcript("m1", WORDS)
    h.add_transcript("m1", FIXED)
    h.undo()
    assert h.transcript_rev("m1") == first
    h.redo()
    assert h.transcripts()["m1"] == FIXED


def test_material_undo_refuses_after_a_later_material_change(tmp_path):
    main = History(tmp_path / "p.kuulas")
    main.add_transcript("m1", WORDS)
    short = History(tmp_path / "p.kuulas", edit=main.create_edit("Short"))
    main.add_transcript("m1", FIXED)
    head = main.head
    # Someone corrected the same material again, from another edit.
    latest = short.add_transcript("m1", AGAIN)
    with pytest.raises(HistoryError) as err:
        main.undo()
    assert err.value.key == "error.history.material_changed"
    assert main.head == head
    assert main.transcript_rev("m1") == latest


def test_transcript_correction_is_seen_by_every_edit(tmp_path):
    main = History(tmp_path / "p.kuulas")
    store = main.db  # media rows are material; register one for the clip below
    store.execute(
        "insert into media(id, sha256, name, storage, channels, source_rate,"
        " source_frames, lossless, added_utc) values"
        " ('m1', 'aa', 'a.wav', 'working', 1, 48000, 4800, 1, '2026-10-16T00:00:00Z')")
    p = ops.add_track(main.state, track_id="t", name="A")
    main.commit("clip", ops.add_clip(p, "t", "m1", clip_id="c"))
    main.add_transcript("m1", WORDS)
    short = History(tmp_path / "p.kuulas", edit=main.create_edit("Short"))
    main.add_transcript("m1", FIXED)
    words = transcript.timeline_words(short.state, short.transcripts())
    assert [w["w"] for w in words] == ["Hei!"]
    assert "transcripts" not in short.state.to_dict()


def test_edits_have_separate_undo(tmp_path):
    main = History(tmp_path / "p.kuulas")
    edit(main, -1.0)
    short = History(tmp_path / "p.kuulas", edit=main.create_edit("Short"))
    assert gain(short) == -1.0  # starts from the current state
    edit(short, -6.0)
    edit(main, -2.0)
    main.undo()
    assert (gain(main), gain(short)) == (-1.0, -6.0)
    assert [e["name"] for e in main.edits()][1:] == ["Short"]


def test_checkpoints_name_a_step(tmp_path):
    h = History(tmp_path / "p.kuulas")
    edit(h, -1.0)
    h.checkpoint("v1 sent to Ville", kind="sent", copy="c0ffee")
    edit(h, -2.0)
    [cp] = h.checkpoints()
    assert (cp["name"], cp["kind"], cp["copy"]) == ("v1 sent to Ville", "sent", "c0ffee")
    assert cp["node"] == h.nodes()[1]["id"]


def heavy_hour() -> Project:
    """docs/FORMAT.md's measured fixture: 4 mono mics, an hour each, 300 ripple
    cuts on all tracks (1,204 clips), 600 automation points."""
    rate, hour = 48000, 3600 * 48000
    p = Project(rate=rate)
    for i in range(4):
        p = ops.add_media(p, Media(id=f"m{i:012x}", name=f"mic{i}.wav", channels=1,
                                   frames=hour, sha256=f"{i:064x}"))
        p = ops.add_track(p, track_id=f"t{i}", name=f"Mic {i}")
        p = ops.add_clip(p, f"t{i}", f"m{i:012x}")
    for k in range(300, 0, -1):
        start = k * 11 * rate
        p = ops.ripple_delete(p, start, start + rate // 2)
    for i in range(4):
        points = [(j * 20 * rate, -3.0 - (j % 7)) for j in range(150)]
        p = ops.set_track_automation(p, f"t{i}", points)
    return p


def test_measured_state_size():
    p = heavy_hour()
    assert sum(len(t.clips) for t in p.tracks) == 1204
    assert sum(len(t.automation) for t in p.tracks) == 600
    _, data = edit_blob(p)
    # FORMAT.md measured 22.7 KB; a model change that bloats states fails here.
    assert len(data) < 30 * 1024, len(data)
