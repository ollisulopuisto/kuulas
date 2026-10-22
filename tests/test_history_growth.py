"""A long history must not make each edit slower (as fast after 4 hours as at launch).

The work is counted in SQLite virtual-machine steps (``set_progress_handler``),
not in milliseconds, so the test does not depend on the machine's speed or load:
the same call on a history 20 times longer must cost about the same.

Measured before the fix (2026-10-22, M1 Max, wall time per call):

| nodes  | coalesced drag step | history page (51) | sides for the page |
|--------|---------------------|-------------------|--------------------|
| 0      | 0.25 ms             | 0.16 ms           | 0.06 ms            |
| 5 000  | 0.46 ms             | 2.8 ms            | 4.6 ms             |
| 20 000 | 2.2 ms              | 13.5 ms           | 25 ms              |
| 50 000 | 4.6 ms              | 34.7 ms           | 78 ms              |

The history panel asks for a page (and its sides) after every edit while it is
open, so at 50 000 steps that was 110 ms per edit, twice the 50 ms budget.
"""

from __future__ import annotations

import random

from kuulas import db as dbm
from kuulas import ops
from kuulas.history import History

SMALL, LARGE = 200, 4000


def grow(h: History, steps: int) -> None:
    with dbm.tx(h.db):
        p = h.state
        for i in range(steps):
            p = ops.set_master(p, -(i % 60) * 0.1)
            h.commit(f"step {i}", p)


def vm_steps(h: History, fn) -> int:
    count = [0]

    def tick() -> int:
        count[0] += 1
        return 0

    h.db.set_progress_handler(tick, 50)
    try:
        fn()
    finally:
        h.db.set_progress_handler(None, 0)
    return count[0]


def cost_at(tmp_path, steps: int, fn) -> int:
    h = History(tmp_path / f"h{steps}.kuulas")
    grow(h, steps)
    return vm_steps(h, lambda: fn(h))


def assert_flat(small: int, large: int) -> None:
    # 20x the history may cost at most 2x (plus a little for a deeper b-tree).
    msg = f"{small} VM steps at {SMALL} nodes, {large} at {LARGE}"
    assert large <= 2 * small + 50, msg


def test_a_coalesced_drag_step_costs_the_same_on_a_long_history(tmp_path):
    def drag(h: History) -> None:
        for i in range(5):
            h.commit("drag", ops.set_master(h.state, -0.05 - i), coalesce="drag")

    assert_flat(cost_at(tmp_path, SMALL, drag), cost_at(tmp_path, LARGE, drag))


def test_the_newest_page_costs_the_same_on_a_long_history(tmp_path):
    def page(h: History) -> None:
        assert len(h.nodes_page(51)) == 51

    assert_flat(cost_at(tmp_path, SMALL, page), cost_at(tmp_path, LARGE, page))


def test_sides_of_a_page_cost_the_same_on_a_long_history(tmp_path):
    def sides(h: History) -> None:
        h.sides()  # the panel's first page: may build what later pages reuse
        h.commit("one more", ops.set_master(h.state, -33.0))
        ids = [r["id"] for r in h.nodes_page(51)]
        assert h.sides(ids)[h.head] == "head"

    def again(h: History) -> int:
        sides(h)
        return vm_steps(h, lambda: sides_only(h))

    def sides_only(h: History) -> None:
        h.commit("and one more", ops.set_master(h.state, -34.0))
        h.sides([r["id"] for r in h.nodes_page(51)])

    small = History(tmp_path / "s.kuulas")
    grow(small, SMALL)
    large = History(tmp_path / "l.kuulas")
    grow(large, LARGE)
    assert_flat(again(small), again(large))


def test_sides_of_some_steps_agree_with_the_whole_map(tmp_path):
    """Random commits, coalesced runs, undo, redo, goto and restore: the sides the
    page asks for always equal the full computation."""
    rng = random.Random(7)  # noqa: S311 - a repeatable test sequence, not a secret
    h = History(tmp_path / "p.kuulas")
    grow(h, 5)
    h.sides([h.head])  # build the incremental map early so every move updates it
    for i in range(400):
        k = rng.random()
        if k < 0.35:
            h.commit(f"e{i}", ops.set_master(h.state, -rng.random() * 20))
        elif k < 0.45:
            h.commit(f"d{i}", ops.set_master(h.state, -rng.random() * 20),
                     coalesce=f"run{i // 3}")
        elif k < 0.65:
            h.undo()
        elif k < 0.8:
            h.redo()
        elif k < 0.9:
            h.goto(rng.choice(h.nodes())["id"])
        else:
            h.restore(rng.choice(h.nodes())["id"])
        full = h.sides()
        some = [*rng.sample(sorted(full), min(len(full), 30)), h.head]
        assert h.sides(some) == {n: full[n] for n in some}, f"after move {i}"


def test_a_reopened_history_gives_the_same_sides(tmp_path):
    h = History(tmp_path / "p.kuulas")
    grow(h, 50)
    for _ in range(10):
        h.undo()
    h.commit("branch", ops.set_master(h.state, -40.0))
    full = h.sides()
    again = History(tmp_path / "p.kuulas")
    assert again.sides(list(full)) == full


def test_undo_redo_and_their_flags_cost_the_same_on_a_long_history(tmp_path):
    """Every API answer carries can_undo and can_redo (children by parent, id order)."""
    def flags(h: History) -> None:
        for _ in range(3):
            h.undo()
        assert h.can_undo
        assert h.can_redo
        for _ in range(3):
            h.redo()

    assert_flat(cost_at(tmp_path, SMALL, flags), cost_at(tmp_path, LARGE, flags))
