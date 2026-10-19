"""Sync asks first (owner, 2026-10-19): the preview says what a moving sync command
would do, changes nothing, and agrees with the real command."""

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from test_server import FakeEngine

from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000
SEC = 10


def _wav(path, seed):
    rng = np.random.default_rng(seed)
    noise = (rng.standard_normal(SEC * RATE) * 0.1).astype(np.float32)
    sf.write(path, noise, RATE, subtype="PCM_16")
    return str(path)


@pytest.fixture
def s(tmp_path):
    session = Session(tmp_path / "Talk.kuulas")
    session.import_media([_wav(tmp_path / f"{n}.wav", i) for i, n in enumerate("avz")])
    p = session.state
    session.clip_of = {}
    for k, name, track in zip("AVZ", ("Anna", "Ville", "Zoom"), p.tracks, strict=True):
        session.edit("set_track", {"track_id": track.id, "name": name})
        session.clip_of[k] = track.clips[0].id
    session.edit("mark_in_sync", {"clip_ids": list(session.clip_of.values()),
                                  "main": session.clip_of["Z"], "group_id": "g"})
    yield session
    session.close()


def drift(s, k, delta):
    s.edit("nudge_clips", {"clip_ids": [s.clip_of[k]], "delta": delta,
                           "group_editing": False})


def starts(s):
    return {c.id: c.start for t in s.state.tracks for c in t.clips}


def real_shifts(before, s):
    after = starts(s)
    return {c: after[c] - at for c, at in before.items() if after[c] != at}


def listed(preview):
    return {m["clip_id"]: m["shift"] for m in preview["moves"]}


def test_preview_changes_nothing_and_lists_the_shifts(s):
    drift(s, "A", 2400)
    drift(s, "V", 600)
    before, head = starts(s), s.history.head
    pv = s.sync_preview("resync", {"clip_ids": list(s.clip_of.values())})
    assert starts(s) == before
    assert s.history.head == head
    assert pv["kind"] == "move"
    assert pv["count"] == 2
    by = {m["clip_id"]: m for m in pv["moves"]}
    assert by[s.clip_of["A"]]["shift"] == -2400
    assert by[s.clip_of["A"]]["track"] == "Anna"
    assert by[s.clip_of["V"]]["shift"] == -600
    assert s.clip_of["Z"] not in by  # clips that stay are not listed
    assert pv["anchor"] == "Zoom"


def test_preview_agrees_with_the_real_command(s):
    drift(s, "A", 2400)
    drift(s, "V", 600)
    before = starts(s)
    pv = s.sync_preview("resync", {"clip_ids": list(s.clip_of.values())})
    s.command("resync", {"clip_ids": list(s.clip_of.values())})
    assert listed(pv) == real_shifts(before, s)


def test_preview_from_the_play_cursor_matches_resync_from(s):
    drift(s, "A", 2400)
    before = starts(s)
    pv = s.sync_preview("resync_from", {"frame": 0})
    s.command("resync_from", {"frame": 0})
    real = real_shifts(before, s)
    assert real
    assert listed(pv) == real


def test_free_clips_are_skipped_and_counted(s):
    drift(s, "A", 2400)
    s.edit("set_free", {"clip_ids": [s.clip_of["A"]], "free": True})
    pv = s.sync_preview("resync", {"clip_ids": [s.clip_of["A"]]})
    assert pv["moves"] == []
    assert pv["count"] == 0
    assert pv["skipped_free"] == 1


def test_nothing_to_move_says_why(s):
    pv = s.sync_preview("resync", {"clip_ids": list(s.clip_of.values())})
    assert pv["kind"] == "nothing"
    assert pv["moves"] == []
    assert pv["message"]


def test_send_home_lists_the_track_change(s):
    s.edit("move_clips_to_track", {"clip_ids": [s.clip_of["A"]], "direction": 1,
                                   "group_editing": False})
    pv = s.sync_preview("send_home", {"clip_ids": [s.clip_of["A"]]})
    assert pv["kind"] == "move"
    assert pv["count"] == 1
    move = pv["moves"][0]
    assert move["shift"] == 0
    assert move["to_track"] == "Anna"
    assert move["track"] != "Anna"


def test_a_command_that_moves_nothing_is_refused(s):
    with pytest.raises(Exception, match="Unknown"):
        s.sync_preview("free", {})


def test_the_endpoint_answers_the_same(s, tmp_path):
    drift(s, "A", 2400)
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(s, FakeEngine(), language="en", ui_dir=ui)) as client:
        answer = client.post("/api/sync/preview", json={
            "name": "resync", "args": {"clip_ids": [s.clip_of["A"]]}}).json()
    assert answer["count"] == 1
    assert answer["moves"][0]["shift"] == -2400
