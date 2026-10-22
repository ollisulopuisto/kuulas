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


# -- what a Restore rolled back (the effective parent of a restore is its target) --------


def test_restore_rolls_back_the_steps_between_its_target_and_the_old_head(tmp_path):
    h = History(tmp_path / "p.kuulas")
    a, b, c = edit(h, -1.0), edit(h, -2.0), edit(h, -3.0)
    h.restore(a)
    r = h.head
    info = h.lineage()
    assert info[r]["side"] == "head"
    assert info[r]["restore_target"] == a
    assert info[a]["side"] == "past"
    assert info[b]["side"] == info[c]["side"] == "rolled_back"
    assert info[b]["rolled_back_by"] == info[c]["rolled_back_by"] == r
    assert info[a]["rolled_back_by"] is None
    assert info[a]["restore_target"] is None
    assert h.sides()[b] == "rolled_back"


def test_restore_of_a_restore_brings_the_rolled_back_steps_back(tmp_path):
    h = History(tmp_path / "p.kuulas")
    a, b, c = edit(h, -1.0), edit(h, -2.0), edit(h, -3.0)
    h.restore(a)
    r1 = h.head
    d = edit(h, -4.0)
    h.restore(c)
    r2 = h.head
    info = h.lineage()
    assert info[r2]["restore_target"] == c
    assert info[c]["side"] == info[b]["side"] == info[a]["side"] == "past"
    assert info[d]["side"] == info[r1]["side"] == "rolled_back"
    assert info[d]["rolled_back_by"] == info[r1]["rolled_back_by"] == r2
    assert info[b]["rolled_back_by"] is None


def test_restore_onto_a_left_behind_step_pulls_its_branch_into_the_state(tmp_path):
    h = History(tmp_path / "p.kuulas")
    a, b, c = edit(h, -1.0), edit(h, -2.0), edit(h, -3.0)
    h.undo()
    h.undo()  # head = a
    d = edit(h, -9.0)  # b, c left behind
    assert h.sides()[c] == "branch"
    h.restore(c)
    r = h.head
    info = h.lineage()
    assert info[c]["side"] == info[b]["side"] == "past"
    assert info[a]["side"] == "past"
    assert info[d]["side"] == "rolled_back"
    assert info[d]["rolled_back_by"] == r


def test_undoing_a_restore_makes_the_rolled_back_steps_current_again(tmp_path):
    h = History(tmp_path / "p.kuulas")
    a, b, c = edit(h, -1.0), edit(h, -2.0), edit(h, -3.0)
    h.restore(a)
    r = h.head
    h.undo()
    info = h.lineage()
    assert info[c]["side"] == "head"
    assert info[b]["side"] == info[a]["side"] == "past"
    assert info[b]["rolled_back_by"] is None
    assert info[r]["side"] == "redo"
    assert info[r]["restore_target"] == a


def test_an_edit_after_undoing_a_restore_leaves_the_restore_behind(tmp_path):
    h = History(tmp_path / "p.kuulas")
    a, b = edit(h, -1.0), edit(h, -2.0)
    h.restore(a)
    r = h.head
    h.undo()
    e = edit(h, -7.0)
    info = h.lineage()
    assert info[e]["side"] == "head"
    assert info[b]["side"] == "past"
    assert info[r]["side"] == "branch"
    assert info[r]["rolled_back_by"] is None


def test_lineage_is_one_query_and_covers_a_long_history(tmp_path):
    h = History(tmp_path / "p.kuulas")
    first = edit(h, -1.0)
    for i in range(300):
        edit(h, -float(i % 40))
    h.restore(first)
    info = h.lineage()
    assert len(info) == 303
    assert sum(1 for v in info.values() if v["side"] == "rolled_back") == 300
