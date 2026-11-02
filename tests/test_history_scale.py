from __future__ import annotations

import time
from pathlib import Path

import pytest

from kuulas import db as dbm
from kuulas import ops
from kuulas.history import History


class TimedDatabase:
    """Test-only SQL phase timings; preserves the real durable connection."""

    def __init__(self, target):
        self.target = target
        self.timings: list[tuple[str, float]] = []

    def execute(self, sql, *args, **kwargs):
        start = time.perf_counter()
        try:
            return self.target.execute(sql, *args, **kwargs)
        finally:
            self.timings.append((sql, time.perf_counter() - start))

    def __getattr__(self, name):
        return getattr(self.target, name)


def measured_operation(history, operation):
    """Return result and diagnostics without changing a wall-clock budget."""
    original = history.db
    database = TimedDatabase(original)
    history.db = database
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    try:
        result = operation()
    finally:
        wall = time.perf_counter() - wall_start
        cpu = time.process_time() - cpu_start
        history.db = original
    sql_wall = sum(duration for _, duration in database.timings)
    commit_wall = sum(duration for sql, duration in database.timings
                      if sql.strip().lower() == "commit")
    detail = (f"wall={wall * 1000:.3f}ms cpu={cpu * 1000:.3f}ms "
              f"sql={sql_wall * 1000:.3f}ms commit={commit_wall * 1000:.3f}ms "
              f"statements={len(database.timings)}")
    return result, wall, database.timings, detail

def make_5000_history(path: Path, steps: int = 5000) -> History:
    """Build a linear history of `steps` commits quickly inside one transaction."""
    h = History(path)
    with dbm.tx(h.db):
        p = h.state
        for i in range(1, steps + 1):
            gain_val = -(i % 60) * 0.1
            p = ops.set_master(p, gain_val)
            h.commit(
                f"step {i}", p, op={"name": "set_master", "args": {"gain_db": gain_val}}
            )
    return h


def test_nodes_page_pagination(tmp_path):
    h = History(tmp_path / "p.kuulas")
    with dbm.tx(h.db):
        p = h.state
        for i in range(1, 121):
            p = ops.set_master(p, -float(i))
            h.commit(
                f"step {i}", p, op={"name": "set_master", "args": {"gain_db": -float(i)}}
            )

    all_nodes_rev = list(reversed(h.nodes()))
    assert len(all_nodes_rev) == 121  # initial commit + 120 steps

    page1 = h.nodes_page(50)
    assert len(page1) == 50
    assert [n["id"] for n in page1] == [n["id"] for n in all_nodes_rev[:50]]
    assert page1[0]["label"] == "step 120"

    page2 = h.nodes_page(50, before=page1[-1]["id"])
    assert len(page2) == 50
    assert [n["id"] for n in page2] == [n["id"] for n in all_nodes_rev[50:100]]

    page3 = h.nodes_page(50, before=page2[-1]["id"])
    assert len(page3) == 21
    assert [n["id"] for n in page3] == [n["id"] for n in all_nodes_rev[100:121]]
    assert page3[-1]["label"] == "new project"

    page4 = h.nodes_page(50, before=page3[-1]["id"])
    assert page4 == []

    # Zero and negative limits return empty
    assert h.nodes_page(0) == []
    assert h.nodes_page(-1) == []


def test_performance_budgets_with_5000_steps(tmp_path):
    db_path = tmp_path / "scale.kuulas"
    t_start = time.perf_counter()
    h = make_5000_history(db_path, steps=5000)
    build_time = time.perf_counter() - t_start
    # The generator helper itself should run quickly (typically < 1s)
    assert build_time < 5.0, f"History generation was too slow: {build_time:.2f}s"

    # 1. Budget: opening under 1 s
    t0 = time.perf_counter()
    opened = History(db_path)
    open_duration = time.perf_counter() - t0
    assert open_duration < 1.0, f"History open took {open_duration:.3f}s (budget: < 1.0s)"
    assert opened.head == h.head

    # 2. Budget: history-panel page under 50 ms
    t0 = time.perf_counter()
    page = opened.nodes_page(50)
    page_duration = time.perf_counter() - t0
    assert len(page) == 50
    msg = f"First page took {page_duration * 1000:.1f}ms (budget: < 50ms)"
    assert page_duration < 0.050, msg

    # Second page
    t0 = time.perf_counter()
    page2 = opened.nodes_page(50, before=page[-1]["id"])
    page2_duration = time.perf_counter() - t0
    assert len(page2) == 50
    msg2 = f"Second page took {page2_duration * 1000:.1f}ms (budget: < 50ms)"
    assert page2_duration < 0.050, msg2

    # Deep page
    all_rev = opened.nodes_page(2500)
    mid_id = all_rev[-1]["id"]
    t0 = time.perf_counter()
    mid_page = opened.nodes_page(50, before=mid_id)
    mid_duration = time.perf_counter() - t0
    assert len(mid_page) == 50
    msg_mid = f"Mid page took {mid_duration * 1000:.1f}ms (budget: < 50ms)"
    assert mid_duration < 0.050, msg_mid

    # 3. Budget: undo and redo in constant time (tested on 5,000 steps, each < 50ms)
    t0 = time.perf_counter()
    assert opened.undo() is not None
    undo_duration = time.perf_counter() - t0
    assert undo_duration < 0.050, f"Undo took {undo_duration * 1000:.1f}ms"

    result, redo_duration, _timings, detail = measured_operation(opened, opened.redo)
    assert result is not None
    print(f"Redo phases: {detail}")
    assert redo_duration < 0.050, f"Redo took {redo_duration * 1000:.1f}ms; {detail}"

    # 4. Budget: an edit's cost independent of history length (< 50 ms)
    p = ops.set_master(opened.state, -10.0)
    t0 = time.perf_counter()
    opened.commit(
        "scale edit", p, op={"name": "set_master", "args": {"gain_db": -10.0}}
    )
    edit_duration = time.perf_counter() - t0
    assert edit_duration < 0.050, f"Edit took {edit_duration * 1000:.1f}ms"


@pytest.mark.parametrize("steps", [50, 5000])
def test_adjacent_redo_has_bounded_sql_work_and_is_durable(tmp_path, steps):
    path = tmp_path / "redo.kuulas"
    original = make_5000_history(path, steps=steps)
    opened = History(path)
    try:
        assert opened.db.execute("pragma synchronous").fetchone()[0] == 2  # FULL
        expected_head = opened.head
        assert opened.undo() is not None
        result, _wall, timings, detail = measured_operation(opened, opened.redo)
        assert result is not None
        # The adjacent-node path must not issue one statement per history step.
        # Current path uses 13 at both lengths; leave headroom for fixed metadata.
        assert len(timings) <= 20, detail
        assert sum(sql.strip().lower() == "commit" for sql, _ in timings) == 1
        reopened = History(path)
        try:
            assert reopened.head == expected_head
            assert reopened.state == opened.state
        finally:
            reopened.db.close()
    finally:
        opened.db.close()
        original.db.close()


def test_phase_diagnostics_identify_slow_commit_without_hiding_wall_time(tmp_path):
    history = make_5000_history(tmp_path / "slow.kuulas", steps=5)
    assert history.undo() is not None
    original = history.db

    class DelayedCommit:
        def execute(self, sql, *args, **kwargs):
            if sql.strip().lower() == "commit":
                time.sleep(0.06)
            return original.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(original, name)

    history.db = DelayedCommit()
    try:
        result, wall, timings, detail = measured_operation(history, history.redo)
        assert result is not None
        assert wall >= 0.06, detail
        assert sum(duration for sql, duration in timings
                   if sql.strip().lower() == "commit") >= 0.06, detail
        # Diagnostics preserve, rather than subtract, the latency the hard gate sees.
        assert "commit=" in detail
        assert history.head is not None
    finally:
        history.db = original
        original.close()
