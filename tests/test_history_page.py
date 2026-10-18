"""Where each step lies relative to the head (WP8 history panel). The route tests are
in test_server.py."""

from kuulas import ops
from kuulas.history import History


def edit(h: History, db: float) -> str:
    h.commit(f"master {db}", ops.set_master(h.state, db))
    return h.head


def test_sides_past_head_redo_and_abandoned_branch(tmp_path):
    h = History(tmp_path / "p.kuulas")
    a, b, c = edit(h, -1.0), edit(h, -2.0), edit(h, -3.0)
    h.undo()
    h.undo()  # head = a; b, c are the redo side
    side = h.sides()
    assert side[h.head] == "head"
    assert side[b] == side[c] == "redo"
    d = edit(h, -9.0)  # a new branch: b and c are abandoned
    side = h.sides()
    assert side[d] == "head"
    assert side[a] == "past"
    assert side[b] == side[c] == "branch"


def test_sides_cover_every_step_of_a_long_history(tmp_path):
    h = History(tmp_path / "p.kuulas")
    for i in range(300):
        edit(h, -float(i % 40))
    assert len(h.sides()) == 301
