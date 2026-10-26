"""Tests for Session.source_map method and GET /api/source-map endpoint."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import messages
from kuulas import source_map as source_map_mod
from kuulas.clock import frames_to_flicks
from kuulas.ops import EditError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


class FakeEngine:
    """Minimal fake engine for create_app."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.position = 0
        self.playing = False
        self.until = None
        self.notices: list[dict] = []

    def status(self):
        return {
            "playing": self.playing,
            "position": self.position,
            "until": self.until,
            "notices": list(self.notices),
        }

    def close(self):
        self.calls.append(("close",))


def make_wav(path: Path, seconds: float = 2.0, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(
        path,
        (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32),
        RATE,
        subtype="PCM_16",
    )
    return path


@pytest.fixture
def split_three_session(tmp_path):
    s = Session(tmp_path / "SourceMap.kuulas")
    f = make_wav(tmp_path / "audio.wav", seconds=2.0, seed=1)
    s.import_media([str(f)], track_per_file=True)
    c1 = s.state.tracks[0].clips[0]

    # Split into 3 pieces: 0..10000, 10000..30000, 30000..96000
    s.edit("split_clip", {"clip_id": c1.id, "at": 10000, "new_id": "c2"})
    s.edit("split_clip", {"clip_id": "c2", "at": 30000, "new_id": "c3"})
    # Mute the middle piece
    s.edit("set_clip", {"clip_id": "c2", "muted": True})

    yield s
    s.close()


def test_session_source_map_split_three_with_middle_muted(split_three_session):
    s = split_three_session
    m = s.state.media[0]
    c1 = s.state.tracks[0].clips[0]

    data = s.source_map(m.sha256)

    assert "clips" in data
    assert "used" in data
    assert "cut" in data
    assert "unused" in data
    assert "parts" in data

    # 3 clips total
    assert len(data["clips"]) == 3
    # parts: 1 of 3, 2 of 3, 3 of 3
    assert data["parts"][c1.id] == [1, 3]
    assert data["parts"]["c2"] == [2, 3]
    assert data["parts"]["c3"] == [3, 3]

    f_10k = frames_to_flicks(10000, RATE)
    f_30k = frames_to_flicks(30000, RATE)
    f_end = frames_to_flicks(96000, RATE)

    # used has two pieces: [0, 10000] and [30000, 96000]
    assert data["used"] == [[0, f_10k], [f_30k, f_end]]
    # cut has middle piece: [10000, 30000]
    assert data["cut"] == [[f_10k, f_30k]]
    # entire recording was covered by clips, so unused is empty
    assert data["unused"] == []


def test_session_source_map_unknown_media_raises_edit_error(split_three_session):
    s = split_three_session
    with pytest.raises(EditError) as exc_info:
        s.source_map("nonexistent_sha256")
    assert exc_info.value.key == "error.edit.no_media"


def test_session_source_map_does_not_hold_lock_during_computation(
    split_three_session, monkeypatch
):
    s = split_three_session
    m = s.state.media[0]

    orig_coverage = source_map_mod.coverage
    lock_free = []

    def probe_coverage(project, media_sha256):
        def try_lock():
            got = s.lock.acquire(timeout=1.0)
            if got:
                s.lock.release()
            lock_free.append(got)

        t = threading.Thread(target=try_lock)
        t.start()
        t.join()
        return orig_coverage(project, media_sha256)

    monkeypatch.setattr(source_map_mod, "coverage", probe_coverage)
    data = s.source_map(m.sha256)
    assert lock_free == [True]
    assert "parts" in data


def test_session_source_map_lock_duration_measurement(tmp_path):
    s = Session(tmp_path / "BenchSourceMap.kuulas")
    files = [
        str(make_wav(tmp_path / f"bench_{i}.wav", seconds=1.0, seed=i))
        for i in range(5)
    ]
    s.import_media(files, track_per_file=True)
    m = s.state.media[0]

    held_durations: list[float] = []
    acq_time: float | None = None

    class LockProxy:
        def __init__(self, target):
            self._target = target

        def acquire(self, *args, **kwargs):
            nonlocal acq_time
            ret = self._target.acquire(*args, **kwargs)
            if ret and acq_time is None:
                acq_time = time.perf_counter()
            return ret

        def release(self, *args, **kwargs):
            nonlocal acq_time
            if acq_time is not None:
                held_durations.append((time.perf_counter() - acq_time) * 1000.0)
                acq_time = None
            return self._target.release(*args, **kwargs)

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *args):
            self.release()

    s.lock = LockProxy(s.lock)

    data = s.source_map(m.sha256)
    # Only what source_map held: close() takes the lock too, to flush the database, and
    # that hold (several ms on a slow disk) is not what this test is about.
    measured = list(held_durations)

    s.close()
    assert "parts" in data
    assert measured, "Lock should have been acquired"
    max_lock_ms = max(measured)
    print(
        f"\nLock held during source_map: {max_lock_ms:.3f} ms "
        f"(durations: {measured})"
    )
    assert max_lock_ms < 5.0  # Lock is held for well under a few milliseconds


def test_source_map_leaves_session_state_and_history_unchanged(split_three_session):
    s = split_three_session
    m = s.state.media[0]
    head_before = s.history.head
    state_before = s.history.state

    s.source_map(m.sha256)

    assert s.history.head == head_before
    assert s.history.state == state_before


def test_api_source_map_success(split_three_session, tmp_path):
    s = split_three_session
    m = s.state.media[0]
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="en", ui_dir=ui)
    client = TestClient(app)

    resp = client.get(f"/api/source-map?media={m.sha256}")
    assert resp.status_code == 200
    data = resp.json()

    assert "clips" in data
    assert "used" in data
    assert "cut" in data
    assert "unused" in data
    assert "parts" in data
    assert len(data["clips"]) == 3


def test_api_source_map_unknown_media_returns_400(split_three_session, tmp_path):
    s = split_three_session
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="en", ui_dir=ui)
    client = TestClient(app)

    resp = client.get("/api/source-map?media=nonexistent")
    assert resp.status_code == 400
    err = resp.json()
    assert err["error"]["key"] == "error.edit.no_media"
    assert "text" in err["error"]


def test_api_source_map_leaves_project_and_history_unchanged(
    split_three_session, tmp_path
):
    s = split_three_session
    m = s.state.media[0]
    head_before = s.history.head
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="en", ui_dir=ui)
    client = TestClient(app)

    resp = client.get(f"/api/source-map?media={m.sha256}")
    assert resp.status_code == 200
    assert s.history.head == head_before
