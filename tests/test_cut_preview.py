"""Tests for cut_preview Session method and POST /api/cut-preview endpoint."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import collateral as collateral_mod
from kuulas import messages
from kuulas.clock import FLICKS
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
    """What the API needs of an Engine: minimal public surface."""

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


def words(*spans):
    """(text, start_s, end_s, speaker) -> stored words in flicks."""
    return [
        {
            "w": w,
            "s": round(s * FLICKS),
            "e": round(e * FLICKS),
            "spk": spk,
        }
        for w, s, e, spk in spans
    ]


@pytest.fixture
def two_track_session(tmp_path):
    s = Session(tmp_path / "CutPreview.kuulas")
    f_a = make_wav(tmp_path / "a.wav", seconds=2.0, seed=1)
    f_b = make_wav(tmp_path / "b.wav", seconds=2.0, seed=2)
    s.import_media([str(f_a), str(f_b)], track_per_file=True)
    m0 = s.state.media[0].id
    m1 = s.state.media[1].id
    s.set_transcript(
        m0,
        words(("hello", 0.1, 0.5, "A"), ("world", 0.6, 1.0, "A")),
        "t_a",
    )
    s.set_transcript(
        m1,
        words(("sorry", 0.2, 0.4, "B"), ("later", 1.2, 1.6, "B")),
        "t_b",
    )
    yield s
    s.close()


def test_session_cut_preview_overlapping_tracks(two_track_session):
    s = two_track_session
    t0 = s.state.tracks[0]
    t1 = s.state.tracks[1]
    c0 = t0.clips[0]

    # Select word "hello" on track 0 (s=0.1s, e=0.5s -> in frames: 4800 to 24000)
    selection = [{"track": t0.id, "clip": c0.id, "index": 0}]

    res = s.cut_preview(selection)

    expected_start = round(0.1 * RATE)
    expected_end = round(0.5 * RATE)

    assert res["span"] == [expected_start, expected_end]
    # Track 1 has "sorry" at 0.2-0.4s inside the 0.1-0.5s span
    assert len(res["other_words"]) == 1
    assert res["other_words"][0]["w"] == "sorry"
    assert res["other_words"][0]["track"] == t1.id

    # Audio on track 1 that disappears with the cut
    assert t1.id in res["audio"]
    assert res["audio"][t1.id] == [[expected_start, expected_end]]


def test_session_cut_preview_empty_selection_raises_edit_error(two_track_session):
    s = two_track_session
    with pytest.raises(EditError) as exc_info:
        s.cut_preview([])
    assert exc_info.value.key == "error.edit.no_selection"

    # Stale/non-matching selection also raises EditError
    with pytest.raises(EditError) as exc_info2:
        s.cut_preview([{"track": "nonexistent", "clip": "c", "index": 99}])
    assert exc_info2.value.key == "error.edit.no_selection"


def test_session_cut_preview_does_not_hold_lock_during_computation(
    two_track_session, monkeypatch
):
    s = two_track_session
    t0 = s.state.tracks[0]
    c0 = t0.clips[0]
    selection = [{"track": t0.id, "clip": c0.id, "index": 0}]

    orig_cut = collateral_mod.cut_collateral
    lock_free = []

    def probe_cut_collateral(project, transcripts, selected):
        # Verify that another thread can acquire session.lock while
        # cut_collateral is running
        def try_lock():
            got = s.lock.acquire(timeout=1.0)
            if got:
                s.lock.release()
            lock_free.append(got)

        t = threading.Thread(target=try_lock)
        t.start()
        t.join()
        return orig_cut(project, transcripts, selected)

    monkeypatch.setattr(collateral_mod, "cut_collateral", probe_cut_collateral)
    res = s.cut_preview(selection)
    assert lock_free == [True]
    assert "span" in res


@pytest.mark.parametrize("slow_close", [False, True])
def test_session_cut_preview_lock_duration_measurement(tmp_path, monkeypatch, slow_close):
    # Benchmark with several transcripts to verify lock is held for only fractions of a ms
    s = Session(tmp_path / "Bench.kuulas")
    files = [
        str(make_wav(tmp_path / f"bench_{i}.wav", seconds=1.0, seed=i)) for i in range(5)
    ]
    s.import_media(files, track_per_file=True)

    # Set 5 transcripts with 100 words each
    for i, m in enumerate(s.state.media):
        word_list = [
            (f"word_{j}", j * 0.01, (j + 1) * 0.01, f"spk_{i}") for j in range(100)
        ]
        s.set_transcript(m.id, words(*word_list), f"t_{i}")

    t0 = s.state.tracks[0]
    c0 = t0.clips[0]
    selection = [{"track": t0.id, "clip": c0.id, "index": 0}]

    # Measure exact time session.lock is held
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
    if slow_close:
        close = s.close

        def delayed_close():
            # Deterministic stand-in for a slow database flush during shutdown.
            # It must not count against cut_preview's unchanged 5 ms budget.
            with s.lock:
                time.sleep(0.02)
            close()

        monkeypatch.setattr(s, "close", delayed_close)

    res = s.cut_preview(selection)
    # Shutdown flushes the database under the same lock. Measure only the
    # operation named by this benchmark, as the source-map benchmark does.
    measured = list(held_durations)

    s.close()
    if slow_close:
        assert max(held_durations) >= 20.0, "slow close must exercise the regression"
    assert "span" in res
    assert measured, "Lock should have been acquired"
    max_lock_ms = max(measured)
    print(
        f"\nLock held during cut_preview: {max_lock_ms:.3f} ms "
        f"(durations: {measured})"
    )
    assert max_lock_ms < 5.0  # Lock is held for well under a few milliseconds


def test_cut_preview_leaves_session_state_and_history_unchanged(two_track_session):
    s = two_track_session
    head_before = s.history.head
    state_before = s.history.state

    t0 = s.state.tracks[0]
    c0 = t0.clips[0]
    s.cut_preview([{"track": t0.id, "clip": c0.id, "index": 0}])

    assert s.history.head == head_before
    assert s.history.state == state_before


def test_api_cut_preview_success(two_track_session, tmp_path):
    s = two_track_session
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="en", ui_dir=ui)
    client = TestClient(app)

    t0 = s.state.tracks[0]
    c0 = t0.clips[0]
    payload = {"words": [{"track": t0.id, "clip": c0.id, "index": 0}]}

    resp = client.post("/api/cut-preview", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert "span" in data
    assert "other_words" in data
    assert "audio" in data
    assert len(data["other_words"]) == 1
    assert data["other_words"][0]["w"] == "sorry"


def test_api_cut_preview_empty_selection_returns_400(two_track_session, tmp_path):
    s = two_track_session
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="en", ui_dir=ui)
    client = TestClient(app)

    resp = client.post("/api/cut-preview", json={"words": []})
    assert resp.status_code == 400
    err = resp.json()
    assert err["error"]["key"] == "error.edit.no_selection"
    assert "text" in err["error"]


def test_api_cut_preview_leaves_project_and_history_unchanged(
    two_track_session, tmp_path
):
    s = two_track_session
    head_before = s.history.head
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="en", ui_dir=ui)
    client = TestClient(app)

    t0 = s.state.tracks[0]
    c0 = t0.clips[0]
    resp = client.post(
        "/api/cut-preview",
        json={"words": [{"track": t0.id, "clip": c0.id, "index": 0}]},
    )
    assert resp.status_code == 200
    assert s.history.head == head_before
