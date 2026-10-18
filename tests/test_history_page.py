"""The history panel's read side (WP8 UI): pages of steps with their place relative to
the head, and what undo and redo report when they cross a session marker."""

from test_server import client, engine, english, loaded, session, wav  # noqa: F401

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


def test_history_page_is_newest_first_and_pages_backwards(client, loaded):  # noqa: F811
    track = loaded["project"]["tracks"][0]["id"]
    for g in (-1.0, -2.0, -3.0):
        client.post("/api/edit", json={"op": "set_track", "label": f"gain {g}",
                                       "args": {"track_id": track, "gain_db": g}})
    first = client.get("/api/history", params={"limit": 2}).json()
    assert [n["label"] for n in first["nodes"]] == ["gain -3.0", "gain -2.0"]
    assert first["head"] == first["nodes"][0]["id"]
    assert first["nodes"][0]["is_head"] is True
    assert first["nodes"][1]["side"] == "past"
    assert first["can_undo"] is True and first["can_redo"] is False
    assert first["more"] is True
    second = client.get("/api/history", params={"limit": 2,
                                                "before": first["nodes"][-1]["id"]}).json()
    assert second["nodes"][0]["label"] == "gain -1.0"
    assert {"id", "label", "created", "author", "is_marker", "op", "parent",
            "side"} <= set(second["nodes"][0])
    assert second["nodes"][0]["op"] == "set_track"
    assert "context" not in second["nodes"][0]
    # the whole of it eventually ends
    last = client.get("/api/history", params={"limit": 50,
                                              "before": second["nodes"][-1]["id"]}).json()
    assert last["more"] is False


def test_history_page_marks_markers_and_the_redo_side(client, session, loaded):  # noqa: F811
    track = loaded["project"]["tracks"][0]["id"]
    client.post("/api/edit", json={"op": "set_track", "label": "quieter",
                                   "args": {"track_id": track, "gain_db": -6.0}})
    session.history.session_closed()
    client.post("/api/undo")
    page = client.get("/api/history", params={"limit": 10}).json()
    marker = page["nodes"][0]
    assert marker["is_marker"] is True and marker["marker"] == "closed"
    assert marker["side"] == "redo"
    assert page["can_redo"] is True


def test_history_page_limit_is_checked(client):
    r = client.get("/api/history", params={"limit": 0})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.server.bad_request"
    r = client.get("/api/history", params={"limit": 100000})
    assert r.status_code == 400


def test_history_without_a_limit_still_lists_everything(client, loaded):  # noqa: F811
    body = client.get("/api/history").json()
    assert body["nodes"][0]["label"] == "new project"


def test_undo_across_a_marker_says_which_step_and_which_marker(client, session, loaded):  # noqa: F811
    track = loaded["project"]["tracks"][0]["id"]
    client.post("/api/edit", json={"op": "set_track", "label": "quieter",
                                   "args": {"track_id": track, "gain_db": -6.0}})
    session.history.session_closed()
    session.history.session_opened()
    undone = client.post("/api/undo").json()
    assert undone["moved"]["direction"] == "undo"
    assert undone["moved"]["step"]["label"] == "quieter"
    assert undone["moved"]["step"]["created"]
    assert undone["moved"]["crossed_marker"] is True
    redone = client.post("/api/redo").json()
    assert redone["moved"]["direction"] == "redo"
    # the markers lie after the step, so redoing it passes none
    assert redone["moved"]["crossed_marker"] is False


def test_undo_without_a_marker_does_not_claim_one(client, loaded):  # noqa: F811
    track = loaded["project"]["tracks"][0]["id"]
    client.post("/api/edit", json={"op": "set_track", "label": "quieter",
                                   "args": {"track_id": track, "gain_db": -6.0}})
    undone = client.post("/api/undo").json()
    assert undone["moved"]["crossed_marker"] is False
    assert undone["moved"]["step"]["label"] == "quieter"


def test_nothing_to_undo_reports_no_move(client):
    assert client.post("/api/undo").json()["moved"] is None
