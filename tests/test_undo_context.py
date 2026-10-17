from __future__ import annotations

from pathlib import Path

from kuulas import ops
from kuulas.history import History
from kuulas.session import Session


def test_context_round_trips(tmp_path: Path):
    h = History(tmp_path / "p.kuulas")
    ctx = {
        "selection": ["c1", "c2"],
        "current_track": "A",
        "playhead": 48000,
        "view": [0, 96000],
        "in": 1000,
        "out": 5000,
    }
    p = ops.add_track(h.state, track_id="A", name="Anna")
    h.commit("add track", p, context=ctx)

    nodes = h.nodes()
    assert len(nodes) == 2
    assert nodes[1]["context"] == ctx

    page = h.nodes_page(10)
    assert page[0]["context"] == ctx


def test_undo_and_redo_return_step_context(tmp_path: Path):
    h = History(tmp_path / "p.kuulas")
    ctx1 = {"selection": ["c1"], "playhead": 1000}
    ctx2 = {"selection": ["c2"], "playhead": 2000}

    p = ops.add_track(h.state, track_id="A", name="Anna")
    h.commit("step 1", p, context=ctx1)
    p = ops.add_track(p, track_id="B", name="Ville")
    h.commit("step 2", p, context=ctx2)

    # Undo step 2 returns ctx2
    res2 = h.undo()
    assert res2 is not None
    assert res2 == ctx2
    assert res2.context == ctx2
    assert res2["selection"] == ["c2"]

    # Redo step 2 returns ctx2
    redo_res = h.redo()
    assert redo_res is not None
    assert redo_res == ctx2
    assert redo_res.context == ctx2

    # Undo step 2 again
    assert h.undo() == ctx2

    # Undo step 1 returns ctx1
    res1 = h.undo()
    assert res1 is not None
    assert res1 == ctx1
    assert res1.context == ctx1

    # Nothing more to undo
    assert h.undo() is None


def test_restore_returns_restored_step_context(tmp_path: Path):
    h = History(tmp_path / "p.kuulas")
    ctx = {"selection": ["c1"], "playhead": 5000}
    p = ops.add_track(h.state, track_id="A", name="Anna")
    h.commit("step 1", p, context=ctx)
    step1_id = h.nodes()[-1]["id"]

    p = ops.add_track(p, track_id="B", name="Ville")
    h.commit("step 2", p, context={"playhead": 9000})

    res = h.restore(step1_id)
    assert res is not None
    assert res.context == ctx
    assert res == ctx


def test_session_markers_on_open_and_close(tmp_path: Path):
    folder = tmp_path / "SessionTest.kuulas"
    s = Session(folder)
    # A newly created project has only the initial step
    assert len(s.history.nodes()) == 1
    assert s.history.nodes()[0]["label"] == "new project"

    # Close writes "closed"
    s.close()

    # Reopening the existing project writes a marker step "opened <Helsinki time>"
    s2 = Session(folder)
    nodes = s2.history.nodes()
    # History: new project -> closed -> opened
    assert len(nodes) == 3
    assert nodes[1]["label"] == "closed"
    assert nodes[1]["op"]["name"] == "marker"
    assert nodes[1]["op"]["args"]["kind"] == "closed"
    open_marker = nodes[2]
    assert open_marker["label"].startswith("opened ")
    assert open_marker["label"].endswith("Helsinki")
    assert open_marker["op"]["name"] == "marker"
    assert open_marker["op"]["args"]["kind"] == "opened"
    s2.close()


def test_crossing_marker_is_reported_on_undo_and_redo(tmp_path: Path):
    folder = tmp_path / "CrossingTest.kuulas"
    s = Session(folder)

    # Edit 1 in first sitting
    ctx1 = {"selection": ["track_A"], "playhead": 100}
    s.history.commit("edit 1", ops.add_track(s.state, track_id="A"), context=ctx1)
    s.close()

    # Second sitting
    s2 = Session(folder)
    ctx2 = {"selection": ["track_B"], "playhead": 200}
    s2.history.commit("edit 2", ops.add_track(s2.state, track_id="B"), context=ctx2)

    # Undo 1: undoes Edit 2 (within second sitting, no marker crossed)
    res1 = s2.undo()
    assert res1 is not None
    assert res1.context == ctx2
    assert res1.marker is None

    # Undo 2: undoes Edit 1 from yesterday, crossing "opened" and "closed" markers!
    res2 = s2.undo()
    assert res2 is not None
    assert res2.context == ctx1
    assert res2.marker is not None
    assert "opened" in res2.marker

    # Redo: redoes Edit 1
    redo1 = s2.redo()
    assert redo1 is not None
    assert redo1.context == ctx1

    # Redo: redoes Edit 2, crossing the session markers back
    redo2 = s2.redo()
    assert redo2 is not None
    assert redo2.context == ctx2
    assert redo2.marker is not None
    s2.close()


def test_old_projects_without_context_still_open(tmp_path: Path):
    h = History(tmp_path / "old.kuulas")
    p = ops.add_track(h.state, track_id="A")
    # Commit with no context
    h.commit("old edit", p)

    # Manually null out context in SQLite if needed
    h.db.execute("update nodes set context=null")

    reopened = History(tmp_path / "old.kuulas")
    nodes = reopened.nodes()
    for n in nodes:
        assert n["context"] is None

    # Undo on a step with no context returns truthy info with context=None
    res = reopened.undo()
    assert res is not None
    assert bool(res) is True
    assert res.context is None
    assert res == {}
