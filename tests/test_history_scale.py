from __future__ import annotations

import time
from pathlib import Path

from kuulas import db as dbm
from kuulas import ops
from kuulas.history import History


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
    assert opened.undo() is True
    undo_duration = time.perf_counter() - t0
    assert undo_duration < 0.050, f"Undo took {undo_duration * 1000:.1f}ms"

    t0 = time.perf_counter()
    assert opened.redo() is True
    redo_duration = time.perf_counter() - t0
    assert redo_duration < 0.050, f"Redo took {redo_duration * 1000:.1f}ms"
