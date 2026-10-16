import sqlite3

from kuulas import ops
from kuulas.history import History
from kuulas.model import Project


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
    assert db.execute("select count(*) from transcripts").fetchone()[0] == 1


def test_history_lists_nodes_with_labels(tmp_path):
    h = History(tmp_path / "p.kuulas")
    edit(h, -1.0)
    nodes = h.nodes()
    assert [n["label"] for n in nodes] == ["new project", "master -1.0"]
    assert nodes[1]["parent"] == nodes[0]["id"]
