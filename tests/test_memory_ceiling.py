"""Memory is O(window), never O(duration) (docs/MEMORY.md).

The incident (2026-10-20, owner's 24 GB MacBook): a 47-minute, 5-track project
swapped the Mac to a forced power-off; the editor held 3 GB and two analysis
workers 1.8 and 1.6 GB. Every 60 s chunk any scan read went into the shared
2 GB cache budget, in the editor and in each worker, so a full scan of a long
project kept up to 2 GB of audio per process.

These tests measure the Python heap (``tracemalloc``, which numpy reports to)
while a path runs over a short and a longer project, and assert that the
peak does not grow with the length: bytes per second of audio, not a fixed
number, so the O(duration) growth is caught on minutes of material.
"""

from __future__ import annotations

import gc
import tracemalloc

import numpy as np
import pytest
import soundfile as sf

from kuulas import analysis, loudness_curve, memory, offload, rss
from kuulas.memory import MemoryBudget
from kuulas.session import Session

RATE = 16000
TRACKS = 2


def write_sources(folder, minutes: float, seed: int) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    frames = round(minutes * 60 * RATE)
    out = []
    for i in range(TRACKS):
        path = folder / f"speaker{i}.wav"
        gain = np.where((np.arange(frames) // (RATE * 3)) % TRACKS == i, 0.2, 0.01)
        sf.write(path, (rng.standard_normal(frames) * gain).astype(np.float32), RATE,
                 subtype="PCM_24")
        out.append(str(path))
    return out


def session_of(tmp_path, minutes: float, seed: int) -> Session:
    s = Session(tmp_path / f"p{seed}.kuulas", rate=RATE)
    s.import_media(write_sources(tmp_path / f"src{seed}", minutes, seed))
    return s


def peak_during(fn) -> int:
    gc.collect()
    tracemalloc.start()
    try:
        fn()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def growth_per_audio_second(tmp_path, run, short=1.0, long=4.0) -> float:
    """Heap peak growth per second of audio (all tracks) between a ``short``
    and a ``long`` project. A cached or whole-file path grows by 4 bytes per
    sample per channel (64 000 B/s per track at 16 kHz); a windowed one by
    the per-hop arrays only (a few hundred bytes per second)."""
    def once(seeds) -> float:
        peaks = []
        for seed, minutes in zip(seeds, (short, long), strict=True):
            s = session_of(tmp_path, minutes, seed)
            try:
                peaks.append(peak_during(lambda s=s: run(s)))
            finally:
                s.close()
        return (peaks[1] - peaks[0]) / ((long - short) * 60 * TRACKS)

    # tracemalloc counts every thread's allocations; a background thread of
    # an earlier test can land in one measurement (seen once in ~10 runs).
    # A real O(duration) path is over the limit in both.
    first = once((1, 2))
    return first if first < MAX_GROWTH else min(first, once((3, 4)))


@pytest.fixture
def fresh_budget(monkeypatch):
    """Each test's stores share a budget of their own (the editor's 2 GB)."""
    budget = MemoryBudget(memory.DEFAULT_LIMIT)
    monkeypatch.setattr(memory, "BUDGET", budget)
    from kuulas import media  # noqa: PLC0415

    monkeypatch.setattr(media, "BUDGET", budget)
    return budget


#: Bytes of heap per second of audio a windowed path may still grow by. Audio
#: itself is 64 000 B/s per track at 16 kHz (float32). What legitimately
#: grows: the level envelope, one float64 per 1.25 ms block (6 400 B/s,
#: ``levels.block_frames``, cached on disk and in the budget), and the per-hop
#: (20 ms) arrays of the lanes and the loudness meter (a few hundred B/s).
#: Measured after the fix: lanes and Auto-Silence ~7 000, curves and peaks
#: under 1 000.
MAX_GROWTH = 12_000


def test_loudness_curves_do_not_grow_with_the_length(tmp_path, fresh_budget):
    def run(s):
        loudness_curve.project_curves(s.state, s.store, None)
    assert growth_per_audio_second(tmp_path, run) < MAX_GROWTH


def test_speech_lanes_do_not_grow_with_the_length(tmp_path, fresh_budget):
    def run(s):
        analysis.speech_lanes(s.state, s.store)
    assert growth_per_audio_second(tmp_path, run) < MAX_GROWTH


def test_auto_silence_does_not_grow_with_the_length(tmp_path, fresh_budget):
    def run(s):
        analysis.silence_ranges(s.state, s.store)
    assert growth_per_audio_second(tmp_path, run) < MAX_GROWTH


def test_waveform_peaks_do_not_grow_with_the_length(tmp_path, fresh_budget):
    def run(s):
        for m in s.state.media:
            for f in (s.store.cache_root / "peaks").glob("*"):
                f.unlink()
            s.store.pyramid(m.id)
    # The pyramid itself is per 256 frames (a few hundred bytes per second).
    assert growth_per_audio_second(tmp_path, run) < MAX_GROWTH


def test_loudness_chunks_are_short_and_give_the_same_answer(tmp_path, fresh_budget,
                                                            monkeypatch):
    # Golden: the 60 s chunks of v26.10.20.4 against the short ones. The meter
    # carries its filter state across chunks, so the curve and the integrated
    # level are the same; true peak is measured per chunk, so a peak exactly
    # at a chunk edge may read a hair lower.
    assert loudness_curve.CHUNK_SEC <= 15
    s = session_of(tmp_path, 2.0, 11)
    try:
        short = loudness_curve.project_curves(s.state, s.store, None)
        monkeypatch.setattr(loudness_curve, "CHUNK_SEC", 60)
        old = loudness_curve.project_curves(s.state, s.store, None)
    finally:
        s.close()
    for a, b in zip([*short["tracks"], short["mix"]], [*old["tracks"], old["mix"]],
                    strict=True):
        assert np.asarray(a["curve"]) == pytest.approx(np.asarray(b["curve"]), abs=0.011)
        assert a["integrated"] == pytest.approx(b["integrated"], abs=0.011)
        assert a["true_peak_db"] == pytest.approx(b["true_peak_db"], abs=0.05)


def test_a_long_scan_leaves_no_audio_in_the_cache_budget(tmp_path, fresh_budget):
    s = session_of(tmp_path, 3.0, 5)
    try:
        loudness_curve.project_curves(s.state, s.store, None)
        analysis.silence_ranges(s.state, s.store)
        chunks = fresh_budget.namespace_bytes("chunks")
    finally:
        s.close()
    assert chunks == 0


def test_cached_chunks_have_their_own_cap(fresh_budget):
    fresh_budget.set_namespace_limit("chunks", 1000)
    for i in range(10):
        fresh_budget.put("chunks", f"k{i}", np.zeros(100, dtype=np.float32))
    fresh_budget.put("levels", "x", np.zeros(500, dtype=np.float32))
    assert fresh_budget.namespace_bytes("chunks") <= 1000
    assert fresh_budget.get("levels", "x") is not None
    assert fresh_budget.get("chunks", "k9") is not None
    assert fresh_budget.get("chunks", "k0") is None


def test_the_default_chunk_cap_is_small():
    # Playback reads ahead through its own window (engine.PREFETCH_S); the
    # store's chunk cache is only a convenience for repeated short reads.
    assert memory.BUDGET.namespace_limit("chunks") <= 256 * 1024**2


def test_playback_read_ahead_is_bounded_however_fast_the_playhead_moves():
    # Shuttle at high speed or a run through the programme faster than the
    # 3 s KEEP_S: the read-ahead must not keep every chunk it ever decoded
    # (tests/manual/test_memory_acceptance.py grew 1.7 -> 2.8 GB, 10 -> 30 min).
    from collections import deque  # noqa: PLC0415

    from kuulas import engine as engine_mod  # noqa: PLC0415

    class Source:
        def read(self, _media_id, _first, count):
            return np.zeros((1, count), dtype=np.float32)

    ahead = engine_mod._SafeStore(Source(), 1000, deque())
    for index in range(500):  # all within the same wall-clock instant
        wanted = {("m", index), ("m", index + 1)}
        for key in sorted(wanted):
            ahead.fill(*key, now=0.0)
        ahead.evict(wanted, now=0.0)
    assert len(ahead.cache) <= 2 + engine_mod.MAX_SPARE_CHUNKS


def test_playback_reads_do_not_fill_the_cache_budget(tmp_path, fresh_budget):
    from collections import deque  # noqa: PLC0415

    from kuulas import engine as engine_mod  # noqa: PLC0415

    s = session_of(tmp_path, 1.0, 9)
    try:
        ahead = engine_mod._SafeStore(s.store, RATE, deque())
        for index in range(6):
            ahead.fill(s.state.media[0].id, index, now=0.0)
        assert fresh_budget.namespace_bytes("chunks") == 0
        assert ahead.cache[(s.state.media[0].id, 0)][0].any()
    finally:
        s.close()


# -- the worker's ceiling ------------------------------------------------------


def test_rss_reads_this_process():
    now = rss.current()
    assert now is not None
    assert 10 * 1024**2 < now < 64 * 1024**3
    # The same number ps gives (ps reports KB, a moment later).
    other = rss.of(__import__("os").getpid())
    assert other is not None
    assert abs(other - now) < 0.1 * now + 16 * 1024**2


def test_the_guard_raises_a_catalog_error_above_the_ceiling():
    from kuulas import priority  # noqa: PLC0415
    from kuulas.messages import KuulasError  # noqa: PLC0415

    guard = rss.Ceiling(limit=1, read=lambda: 2)
    with pytest.raises(KuulasError) as e:
        guard.check()
    assert e.value.key == "error.offload.memory"
    priority.set_memory_guard(guard.check)
    try:
        with pytest.raises(KuulasError):
            priority.checkpoint()
    finally:
        priority.set_memory_guard(None)
    priority.checkpoint()  # no guard: nothing raised


def test_the_guard_notes_the_peak():
    seen = iter([100, 300, 200])
    guard = rss.Ceiling(limit=1000, read=lambda: next(seen))
    for _ in range(3):
        guard.check()
    assert guard.peak == 300


def test_the_worker_reports_its_peak(tmp_path):
    reply = __import__("kuulas.analysis_worker", fromlist=["run_task"]).run_task(
        {"task": "_probe", "probe": {"what": "spin", "seconds": 0.01}})
    assert reply["peak_rss"] > 0


def test_a_memory_failure_backs_off_and_starts_no_worker(monkeypatch):
    # The worker answers with the catalog error; the editor raises it and the
    # same task starts no new worker during the back-off: no retry storm.
    from kuulas.messages import KuulasError  # noqa: PLC0415

    runs = []

    def fake_run(payload, *_a, **_k):
        runs.append(payload["task"])
        return {"error": {"key": "error.offload.memory",
                          "params": {"mb": 1600, "limit_mb": 1536},
                          "module": "kuulas.messages", "cls": "KuulasError"},
                "peak_rss": 1600 * 1024**2}

    monkeypatch.setattr(offload, "MODE", "process")
    monkeypatch.setattr(offload, "store_spec", lambda _s: {"folder": "/x"})
    monkeypatch.setattr(offload, "_run", fake_run)
    monkeypatch.setattr(offload, "MANAGER", offload.WorkerManager())
    monkeypatch.setattr(offload, "WORKER_PEAKS", {"last": 0, "max": 0})
    with pytest.raises(KuulasError) as first:
        offload.call("speech_lanes", None, object())
    assert first.value.key == "error.offload.memory"
    with pytest.raises(KuulasError) as second:
        offload.call("speech_lanes", None, object())
    assert second.value.key == "error.offload.backoff"
    assert runs == ["speech_lanes"]
    assert offload.WORKER_PEAKS["max"] == 1600 * 1024**2


def test_the_editor_warns_once_above_its_limit_then_per_step(caplog):
    readings = iter([1, 5, 6, 9, 9])
    watch = memory.RssWatch(lambda: next(readings), limit=4, step=3)
    assert [watch.check() for _ in range(5)] == [False, True, False, True, False]
    assert "log.memory.high" not in caplog.text  # translated, not the key


def test_the_performance_report_names_the_workers_peak(monkeypatch):
    from kuulas import profiler  # noqa: PLC0415

    monkeypatch.setattr(offload, "WORKER_PEAKS", {"last": 2**29, "max": 2**30})
    facts = profiler.memory_facts()
    assert facts["worker_max"] == 2**30
    assert isinstance(facts["namespaces"], dict)
    report = profiler.build_report(
        result=profiler.Sampler().result(), interval=0.02, wall=1.0, started="x",
        build="b", python="p", platform="pl", cpu=None, rss=(None, None),
        memory=facts, facts=[], counters={}, home=__import__("pathlib").Path("/nowhere"))
    assert "analysis worker peak RSS" in report
    assert "1.00 GiB" in report
