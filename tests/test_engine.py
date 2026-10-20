"""Playback engine (WP2), without an audio device.

sounddevice's ``OutputStream`` is replaced by ``FakeStream``, which records
how it was opened and lets a test run the audio callback by hand
(``pump``), report an underflow, or die the way a vanished device does.
The engine's helper thread is off (``background=False``); tests call
``_tick`` themselves with a fake clock, so nothing depends on timing.
"""

import gc
import hashlib
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import sounddevice as sd
import soundfile as sf

from kuulas import messages, mixer, ops, preview_level
from kuulas.engine import Engine, EngineError
from kuulas.media import CHUNK_SEC, MediaStore
from kuulas.model import Media, Project
from kuulas.session import Session

RATE = 48000
ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
CENTRE = np.sqrt(0.5)  # a centred mono clip, constant-power pan


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


# -- fakes -------------------------------------------------------------------


class MemoryStore:
    def __init__(self, arrays: dict[str, np.ndarray]):
        self.arrays = arrays
        self.reads: list[tuple[str, int, int]] = []

    def read(self, media_id: str, first: int, count: int) -> np.ndarray:
        self.reads.append((media_id, first, count))
        a = self.arrays[media_id]
        out = np.zeros((a.shape[0], count), dtype=np.float32)
        lo, hi = max(0, first), min(a.shape[1], first + count)
        if hi > lo:
            out[:, lo - first:hi - first] = a[:, lo:hi]
        return out


class FakeSession:
    """What the engine needs of a Session: state, store, lock, subscribe."""

    def __init__(self, project: Project, store):
        self.state = project
        self.store = store
        self.lock = threading.RLock()
        self.listeners = []

    def subscribe(self, fn):
        self.listeners.append(fn)

    def change(self, project: Project):
        self.state = project
        for fn in self.listeners:
            fn(project)


class FakeStream:
    def __init__(self, rig, **kwargs):
        if kwargs["samplerate"] in rig.refused_rates:
            raise sd.PortAudioError("Invalid sample rate", -9997)
        self.kwargs = kwargs
        self.callback = kwargs["callback"]
        self.finished = kwargs.get("finished_callback")
        self.samplerate = kwargs["samplerate"]
        self.blocksize = kwargs["blocksize"]
        self.latency = rig.latency
        self.active = False
        self.closed = False
        rig.streams.append(self)

    def start(self):
        self.active = True

    def _halt(self):
        was, self.active = self.active, False
        if was and self.finished is not None:
            self.finished()

    def stop(self):
        self._halt()

    def abort(self):
        self._halt()

    def close(self):
        self._halt()
        self.closed = True

    def pump(self, frames: int | None = None, underflow: bool = False) -> np.ndarray:
        """Run the audio callback once, as PortAudio would."""
        frames = frames or self.blocksize
        out = np.full((frames, 2), np.nan, dtype=np.float32)
        self.callback(out, frames, None, SimpleNamespace(output_underflow=underflow))
        return out

    def die(self):
        """The device went away: PortAudio finishes the stream by itself."""
        self._halt()


class Rig:
    def __init__(self):
        self.streams: list[FakeStream] = []
        self.latency = 0.0
        self.refused_rates: set[int] = set()
        self.device_rate = 48000.0
        self.no_device = False
        self.refreshes = 0
        self.name = "Fake Out"

    @property
    def stream(self) -> FakeStream:
        return self.streams[-1]


def install_rig(monkeypatch) -> Rig:
    """Replace sounddevice's stream and device queries with the fakes (also
    used by the skip and tape-rate tests)."""
    r = Rig()
    monkeypatch.setattr(sd, "OutputStream", lambda **kw: FakeStream(r, **kw))

    def query(device=None, kind=None):
        assert kind == "output"
        if r.no_device:
            raise sd.PortAudioError("Error querying device -1", -9996)
        return {"name": r.name, "default_samplerate": r.device_rate,
                "max_output_channels": 2}

    def refresh():
        r.refreshes += 1

    monkeypatch.setattr(sd, "query_devices", query)
    monkeypatch.setattr(sd, "_terminate", lambda: None)
    monkeypatch.setattr(sd, "_initialize", refresh)
    return r


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


def project_with(arrays: dict[str, np.ndarray], rate: int = RATE,
                 starts: dict[str, int] | None = None) -> Project:
    """One track per media, one clip each at ``starts[id]`` (default 0)."""
    p = Project(rate=rate)
    for media_id, a in arrays.items():
        p = ops.add_media(p, Media(id=media_id, name=f"{media_id}.wav",
                                   channels=a.shape[0], frames=a.shape[1]))
        p = ops.add_track(p, f"t-{media_id}", media_id)
        p = ops.add_clip(p, f"t-{media_id}", media_id,
                         start=(starts or {}).get(media_id, 0), clip_id=f"c-{media_id}")
    return p


def noise(seconds: float, channels: int = 1, seed: int = 0, rate: int = RATE):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal((channels, round(seconds * rate))) * 0.1).astype(
        np.float32)


def make(rig, clock, arrays=None, **kwargs):
    arrays = arrays or {"m": noise(2)}
    store = MemoryStore(arrays)
    project = project_with(arrays)
    session = FakeSession(project, store)
    engine = Engine(session, background=False, clock=clock, **kwargs)
    return engine, session, store


def notice_keys(engine) -> list[str]:
    return [n["key"] for n in engine.status()["notices"]]


def wav(path: Path, seconds: float, seed: int = 0) -> Path:
    sf.write(path, noise(seconds, seed=seed)[0], RATE, subtype="PCM_24")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


# -- rendering ---------------------------------------------------------------


def test_stream_opens_stereo_float_with_a_1024_frame_buffer_at_the_project_rate(
        rig, clock):
    engine, _, _ = make(rig, clock)
    assert rig.streams == []  # nothing is opened until the first play
    engine.play(0)
    kw = rig.stream.kwargs
    assert (kw["samplerate"], kw["channels"], kw["dtype"]) == (RATE, 2, "float32")
    # "low" first (precise cursor, 2026-10-20); late blocks raise it to "high"
    # (test_engine_anchor.py)
    assert (kw["blocksize"], kw["latency"]) == (1024, "low")
    assert rig.stream.active
    assert engine.status()["blocksize"] == 1024


def test_render_advances_the_position(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(0)
    out = engine._render(1024)
    assert out.shape == (1024, 2)
    assert out.dtype == np.float32
    np.testing.assert_array_equal(out, mixer.mix(session.state, store, 0, 1024).T)
    out = engine._render(1024)
    np.testing.assert_array_equal(out, mixer.mix(session.state, store, 1024, 1024).T)
    status = engine.status()
    assert status["playing"]
    assert status["position"] == 2048


def test_the_callback_writes_the_rendered_block(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(0)
    out = rig.stream.pump()
    np.testing.assert_array_equal(out, mixer.mix(session.state, store, 0, 1024).T)


def test_render_stops_at_until_and_pads_with_silence(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(at=1000, until=1500)
    assert engine.status()["until"] == 1500
    out = engine._render(1024)
    np.testing.assert_array_equal(out[:500], mixer.mix(session.state, store, 1000, 500).T)
    assert not out[500:].any()
    status = engine.status()
    assert not status["playing"]
    assert status["position"] == 1500
    assert not engine._render(1024).any()  # stopped: silence, position kept
    assert engine.status()["position"] == 1500


def test_play_to_the_end_stops_and_leaves_the_playhead_at_the_end(rig, clock):
    engine, session, store = make(rig, clock, {"m": noise(1)})
    engine.play(RATE - 1000)
    out = engine._render(2048)
    np.testing.assert_array_equal(out[:1000],
                                  mixer.mix(session.state, store, RATE - 1000, 1000).T)
    assert not out[1000:].any()
    status = engine.status()
    assert not status["playing"]
    assert status["position"] == RATE


def test_seek_while_playing_moves_the_position(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(0)
    engine._render(1024)
    engine.seek(10000)
    out = engine._render(512)
    np.testing.assert_array_equal(out, mixer.mix(session.state, store, 10000, 512).T)
    assert engine.status()["position"] == 10512


def test_seek_while_stopped_sets_where_play_starts(rig, clock):
    engine, session, store = make(rig, clock)
    engine.seek(7000)
    assert engine.status()["position"] == 7000
    engine.play()
    out = engine._render(256)
    np.testing.assert_array_equal(out, mixer.mix(session.state, store, 7000, 256).T)


def test_reported_position_subtracts_output_latency(rig, clock):
    rig.latency = 0.02  # 960 frames at 48 kHz
    engine, _, _ = make(rig, clock)
    engine.play(0)
    assert engine.status()["position"] == 0  # never before where play started
    for _ in range(4):
        engine._render(1024)
    assert engine.status()["position"] == 4096 - 960


def test_stop_leaves_the_playhead_where_it_was_heard(rig, clock):
    rig.latency = 0.01  # 480 frames
    engine, session, store = make(rig, clock)
    engine.play(0)
    for _ in range(4):
        engine._render(1024)
    engine.stop()
    status = engine.status()
    assert not status["playing"]
    assert status["position"] == 4096 - 480
    assert not engine._render(1024).any()
    engine.play()
    out = engine._render(100)
    np.testing.assert_array_equal(out, mixer.mix(session.state, store, 3616, 100).T)


def test_scrub_plays_a_short_stretch_from_the_frame(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.scrub(5000)
    status = engine.status()
    assert status["playing"]
    assert 5000 < status["until"] <= 5000 + RATE // 10
    for _ in range(10):
        engine._render(1024)
    after = engine.status()
    assert not after["playing"]
    assert after["position"] == status["until"]


def test_levels_follow_the_heard_block(rig, clock):
    loud, quiet = 0.8, 0.1
    a = np.full((1, 4096), quiet, dtype=np.float32)
    a[0, :1024] = loud
    a[0, 2048:] = loud
    rig.latency = 1500 / RATE
    engine, _, _ = make(rig, clock, {"m": a})
    engine.play(0)
    for _ in range(3):
        engine._render(1024)
    levels = engine.levels()
    assert levels["position"] == 3072 - 1500  # inside the quiet block
    np.testing.assert_allclose(levels["peak"], [quiet * CENTRE] * 2, rtol=1e-6)


def test_set_project_is_heard_in_the_next_block(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(0)
    engine._render(1024)
    louder = ops.set_track(session.state, "t-m", gain_db=6.0)
    session.change(louder)
    out = engine._render(1024)
    np.testing.assert_array_equal(out, mixer.mix(louder, store, 1024, 1024).T)


# -- previewing a temporary project (clipboard entry, WP46) -------------------


def preview_of(session):
    """A stand-in temporary project: the real one with a quieter track."""
    return ops.set_track(session.state, "t-m", gain_db=-6.0)


def test_preview_plays_the_temporary_project_not_the_real_one(rig, clock):
    engine, session, store = make(rig, clock)
    engine.seek(5000)
    temp = preview_of(session)
    engine.play_preview(temp)
    out = engine._render(1024)
    np.testing.assert_array_equal(out, mixer.mix(temp, store, 0, 1024).T)
    assert engine.status()["preview"] is True
    assert session.state.tracks[0].gain_db == 0.0


def test_only_a_limited_preview_is_held_under_the_ceiling(rig, clock):
    engine, session, _ = make(rig, clock)
    loud = ops.set_track(session.state, "t-m", gain_db=24.0)
    engine.play_preview(loud, limit=True)
    out = engine._render(1024)
    assert np.abs(out).max() <= 10 ** (preview_level.CEILING_DB / 20) + 1e-6
    engine.play_preview(loud)
    assert np.abs(engine._render(1024)).max() > 1.0


def test_an_edit_during_preview_is_remembered_not_played(rig, clock):
    engine, session, store = make(rig, clock)
    temp = preview_of(session)
    engine.play_preview(temp)
    louder = ops.set_track(session.state, "t-m", gain_db=6.0)
    session.change(louder)
    out = engine._render(1024)
    np.testing.assert_array_equal(out, mixer.mix(temp, store, 0, 1024).T)
    engine.stop()
    assert engine.status()["preview"] is False
    engine.play(0)
    out = engine._render(1024)
    np.testing.assert_array_equal(out, mixer.mix(louder, store, 0, 1024).T)


def test_stop_ends_the_preview_and_puts_the_playhead_back(rig, clock):
    engine, session, _ = make(rig, clock)
    engine.seek(5000)
    engine.play_preview(preview_of(session))
    engine._render(1024)
    engine.stop()
    status = engine.status()
    got = (status["preview"], status["playing"], status["position"])
    assert got == (False, False, 5000)


def test_a_preview_that_runs_out_ends_itself(rig, clock):
    engine, session, _ = make(rig, clock)
    engine.seek(700)
    engine.play_preview(preview_of(session), until=2048)
    for _ in range(4):
        engine._render(1024)
    status = engine.status()
    got = (status["preview"], status["playing"], status["position"])
    assert got == (False, False, 700)


def test_play_during_a_preview_plays_the_real_project(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play_preview(preview_of(session))
    engine.play(0)
    assert engine.status()["preview"] is False
    out = engine._render(1024)
    np.testing.assert_array_equal(out, mixer.mix(session.state, store, 0, 1024).T)


# -- with a real session -----------------------------------------------------


def test_edit_during_playback_is_heard_in_the_next_block(rig, clock, session, tmp_path):
    session.import_media([str(wav(tmp_path / "a.wav", 1))])
    track = session.state.tracks[0].id
    engine = Engine(session, background=False, clock=clock)
    engine.play(0)
    before = engine._render(1024)
    assert before.any()
    session.edit("set_track", {"track_id": track, "gain_db": -6.0})
    after = engine._render(1024)
    np.testing.assert_array_equal(
        after, mixer.mix(session.state, session.store, 1024, 1024).T)
    unedited = mixer.mix(ops.set_track(session.state, track, gain_db=0.0),
                         session.store, 1024, 1024).T
    np.testing.assert_allclose(after, unedited * 10 ** (-6 / 20), rtol=1e-5, atol=1e-7)


def test_render_never_takes_the_session_lock(rig, clock, session, tmp_path):
    session.import_media([str(wav(tmp_path / "a.wav", 1))])
    engine = Engine(session, background=False, clock=clock)
    engine.play(0)
    held, release = threading.Event(), threading.Event()

    def hold():
        with session.lock:
            held.set()
            release.wait(10)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait(5)
    done = []
    renderer = threading.Thread(target=lambda: done.append(engine._render(1024)))
    renderer.start()
    renderer.join(2)
    release.set()
    holder.join()
    assert not renderer.is_alive(), "_render waited for the session lock"
    assert done[0].any()


# -- prefetch ----------------------------------------------------------------


def test_prefetch_decodes_the_next_five_seconds(rig, clock):
    arrays = {"m": noise(20), "late": noise(2, seed=1)}
    store = MemoryStore(arrays)
    project = project_with(arrays, starts={"m": RATE, "late": 14 * RATE})
    engine = Engine(FakeSession(project, store), background=False, clock=clock)
    engine.play(8 * RATE)  # clip "m" starts at 1 s: source 7 s .. 12 s
    # (playing warms 2 s, the helper's tick the rest: chunks 0 and 1 together)
    engine._tick()
    step = CHUNK_SEC * RATE
    touched = {first // step for media_id, first, _ in store.reads if media_id == "m"}
    assert touched == {0, 1}
    assert all(first < 12 * RATE for _, first, _ in store.reads)
    assert not [r for r in store.reads if r[0] == "late"]  # starts at 14 s


def test_prefetch_thread_runs_while_playing(rig):
    arrays = {"m": noise(25)}
    store = MemoryStore(arrays)
    engine = Engine(FakeSession(project_with(arrays), store))
    try:
        engine.play(8 * RATE)  # warms chunk 0; the thread reads chunk 1
        store.reads.clear()
        deadline = time.monotonic() + 3
        while not store.reads and time.monotonic() < deadline:
            time.sleep(0.02)
        assert store.reads, "the prefetch thread did not read ahead"
    finally:
        engine.close()
    assert rig.stream.closed


# -- read-ahead: the callback never reads the disk -----------------------------


class ReadSpy(MemoryStore):
    """A store that notes reads and can pretend to be a slow disk."""

    def __init__(self, arrays):
        super().__init__(arrays)
        self.delay = 0.0

    def read(self, media_id, first, count):
        time.sleep(self.delay)
        return super().read(media_id, first, count)


def test_play_warms_the_first_seconds_before_any_callback(rig, clock):
    arrays = {"m": noise(25)}
    store = ReadSpy(arrays)
    engine = Engine(FakeSession(project_with(arrays), store), background=False,
                    clock=clock)
    engine.play(0)
    assert store.reads, "nothing was read ahead when playing started"
    store.reads.clear()
    for _ in range(20):
        rig.stream.pump()
    assert not store.reads, "the callback read from the store"


def test_the_callback_never_reads_even_across_a_chunk_boundary(rig, clock):
    arrays = {"m": noise(25)}
    store = ReadSpy(arrays)
    engine = Engine(FakeSession(project_with(arrays), store), background=False,
                    clock=clock)
    engine.play(CHUNK_SEC * RATE - 3000)
    store.reads.clear()
    store.delay = 0.05  # a read in the callback would now be audible as a stall
    out = np.concatenate([engine._render(1024) for _ in range(10)])
    assert not store.reads
    assert np.std(out) > 0.01  # both sides of the boundary play


def test_seek_warms_the_new_place_so_the_callback_finds_it(rig, clock):
    arrays = {"m": noise(25)}
    store = ReadSpy(arrays)
    engine = Engine(FakeSession(project_with(arrays), store), background=False,
                    clock=clock)
    engine.play(0)
    engine.seek(18 * RATE)
    store.reads.clear()
    out = engine._render(1024)
    assert not store.reads
    assert np.std(out) > 0.01


def test_play_with_a_loop_warms_the_loops_start(rig, clock):
    arrays = {"m": noise(25)}
    store = ReadSpy(arrays)
    engine = Engine(FakeSession(project_with(arrays), store), background=False,
                    clock=clock)
    engine.play(0, loop=(12 * RATE, 14 * RATE))
    assert any(first // (CHUNK_SEC * RATE) == 1 for _, first, _ in store.reads)


def test_a_miss_plays_silence_for_that_source_and_is_counted(rig, clock):
    arrays = {"m": noise(3), "n": noise(3, seed=1)}
    store = ReadSpy(arrays)
    session = FakeSession(project_with({"m": arrays["m"]}), store)
    engine = Engine(session, background=False, clock=clock, debug=True)
    engine.play(0)
    session.change(project_with(arrays))  # "n" has not been read ahead yet
    store.reads.clear()
    cold = engine._render(1024)
    assert not [r for r in store.reads if r[0] == "n"], "the callback read a cold source"
    assert np.std(cold) > 0.01  # "m" still plays
    rig.stream.pump()
    assert engine.status()["debug"]["miss"] >= 1
    engine._tick()  # the helper catches up
    engine.seek(0)
    assert engine.status()["debug"]["miss"] >= 1
    store.reads.clear()
    engine._render(1024)
    assert not store.reads


def test_the_switch_interval_is_short_while_the_stream_is_open(rig, clock):
    before = sys.getswitchinterval()
    engine, _, _ = make(rig, clock)
    try:
        engine.play(0)
        assert sys.getswitchinterval() == pytest.approx(0.0005)
    finally:
        engine.close()
    assert sys.getswitchinterval() == pytest.approx(before)


def test_play_freezes_start_up_objects_out_of_the_collector(rig, clock, monkeypatch):
    frozen = []
    monkeypatch.setattr(gc, "freeze", lambda: frozen.append(1))
    engine, _, _ = make(rig, clock)
    engine.play(0)
    engine.stop()
    engine.play(0)
    assert frozen == [1], "freeze once per engine, not per play"


# -- fault tolerance ---------------------------------------------------------


def test_no_output_device_raises_and_the_engine_still_works_later(rig, clock):
    rig.no_device = True
    engine, _, _ = make(rig, clock)
    with pytest.raises(EngineError) as caught:
        engine.play(0)
    assert caught.value.key == "error.engine.no_device"
    assert not engine.status()["playing"]
    rig.no_device = False
    engine.play(0)
    assert engine.status()["playing"]


def test_a_failing_block_plays_silence_is_counted_and_reported(rig, clock, monkeypatch):
    engine, _, _ = make(rig, clock)
    engine.play(0)

    def broken(*_args, **_kwargs):
        raise RuntimeError("mixer bug")

    real_mix = mixer.mix
    monkeypatch.setattr(mixer, "mix", broken)
    out = rig.stream.pump()  # must not raise
    assert np.array_equal(out, np.zeros_like(out))
    monkeypatch.setattr(mixer, "mix", real_mix)
    assert engine.status()["failed_blocks"] == 1
    engine._tick()
    assert "notice.engine.block_failed" in notice_keys(engine)
    assert rig.stream.active
    assert rig.stream.pump().any()  # the stream kept running


def test_underflows_raise_the_buffer_then_report_struggling(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0)
    first = rig.stream
    first.pump(underflow=True)
    first.pump(underflow=True)
    engine._tick()
    assert len(rig.streams) == 2
    assert first.closed
    assert rig.stream.blocksize == 2048
    assert rig.stream.active
    status = engine.status()
    assert status["playing"]
    assert status["blocksize"] == 2048
    assert status["late_blocks"] == 2
    struggling = [n for n in status["notices"] if n["key"] == "notice.engine.struggling"]
    assert struggling
    assert "2048" in struggling[-1]["text"]

    clock.now += 10
    rig.stream.pump(underflow=True)
    rig.stream.pump(underflow=True)
    engine._tick()
    assert len(rig.streams) == 2  # 2048 is the most it raises to
    again = [n for n in engine.status()["notices"]
             if n["key"] == "notice.engine.struggling"]
    assert again[-1]["id"] > struggling[-1]["id"]  # shown again, never silent


def test_a_single_underflow_is_counted_but_changes_nothing(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0)
    rig.stream.pump(underflow=True)
    engine._tick()
    assert len(rig.streams) == 1
    assert engine.status()["late_blocks"] == 1


def test_stream_finishing_unexpectedly_pauses_and_reopens_the_default_device(
        rig, clock):
    rig.latency = 0.01
    engine, _, _ = make(rig, clock)
    engine.play(0)
    for _ in range(4):
        rig.stream.pump()
    old = rig.stream
    rig.name = "Built-in Speakers"
    old.die()
    engine._tick()
    status = engine.status()
    assert not status["playing"]  # never a dead stream with play still on
    assert status["position"] == 4096 - 480
    assert len(rig.streams) == 2
    assert rig.stream.kwargs["device"] is None
    assert rig.refreshes >= 1  # PortAudio re-read the device list
    changed = [n for n in status["notices"] if n["key"] == "notice.engine.device_changed"]
    assert "Built-in Speakers" in changed[-1]["text"]
    engine.play()
    assert engine.status()["playing"]
    assert len(rig.streams) == 2


def test_device_lost_and_none_left_is_reported(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0)
    rig.no_device = True
    rig.stream.die()
    engine._tick()
    assert not engine.status()["playing"]
    assert "error.engine.no_device" in notice_keys(engine)
    with pytest.raises(EngineError):
        engine.play()


def test_stopping_or_closing_on_purpose_is_not_a_device_change(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0)
    engine.stop()
    engine._tick()
    assert len(rig.streams) == 1
    assert "notice.engine.device_changed" not in notice_keys(engine)


def test_device_refusing_the_project_rate_gets_resampled_output(rig, clock):
    rig.refused_rates = {RATE}
    rig.device_rate = 44100.0
    t = np.arange(2 * RATE) / RATE
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t))[None, :].astype(np.float32)
    engine, _, _ = make(rig, clock, {"m": tone})
    engine.play(0)
    assert rig.stream.samplerate == 44100
    status = engine.status()
    assert status["resampling"]
    assert status["device_rate"] == 44100
    resampling = [n for n in status["notices"] if n["key"] == "notice.engine.resampling"]
    assert "44100" in resampling[-1]["text"]
    out = np.concatenate([rig.stream.pump(441) for _ in range(100)])  # 1 s
    assert abs(engine.status()["position"] - RATE) <= 2
    spectrum = np.abs(np.fft.rfft(out[4410:, 0]))
    peak_hz = np.argmax(spectrum) * 44100 / len(out[4410:])
    assert abs(peak_hz - 1000) < 5
    rms = np.sqrt(np.mean(out[4410:, 0] ** 2))
    assert rms == pytest.approx(0.5 * CENTRE / np.sqrt(2), rel=0.01)


def test_damaged_chunk_plays_silence_and_marks_the_media(rig, clock, session, tmp_path,
                                                         monkeypatch):
    session.import_media([str(wav(tmp_path / "long.wav", 25))])
    media_id = session.state.media[0].id
    real_chunk = MediaStore._chunk

    def chunk(self, mid, index):
        if index == 1:
            raise sf.LibsndfileError(0, "FLAC decode error")
        return real_chunk(self, mid, index)

    monkeypatch.setattr(MediaStore, "_chunk", chunk)
    boundary = CHUNK_SEC * RATE
    # Playback reads past the chunk cache (media.streaming): the same decode
    # error there.
    real_direct = MediaStore._read_direct

    def direct(self, mid, lo, hi, out, at):
        if lo < 2 * boundary and hi > boundary:
            raise sf.LibsndfileError(0, "FLAC decode error")
        return real_direct(self, mid, lo, hi, out, at)

    monkeypatch.setattr(MediaStore, "_read_direct", direct)
    engine = Engine(session, background=False, clock=clock)
    engine.play(boundary - 5000)
    out = np.concatenate([engine._render(1024) for _ in range(20)])
    assert np.std(out[:5000]) > 0.01  # chunk 0 still plays
    assert not out[5000:].any()  # chunk 1 is silence
    status = engine.status()
    assert status["playing"]
    assert status["failed_blocks"] == 0
    assert status["damaged"] == [media_id]
    engine.seek(2 * boundary + 1000)
    assert np.std(engine._render(1024)) > 0.01  # chunk 2 plays again
    engine._tick()
    damaged = [n for n in engine.status()["notices"]
               if n["key"] == "notice.engine.media_damaged"]
    assert "long.wav" in damaged[-1]["text"]


def test_watchdog_restarts_a_stalled_stream(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0)
    rig.stream.pump()
    clock.now += 0.5
    engine._tick()
    assert len(rig.streams) == 1  # half a second is not a stall
    clock.now += 1.0
    engine._tick()
    assert len(rig.streams) == 2
    assert rig.streams[0].closed
    assert rig.stream.active
    assert engine.status()["playing"]
    assert "notice.engine.restarted" in notice_keys(engine)


def test_idle_stream_closes_and_the_next_play_reads_the_device_list_again(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0)
    engine.stop()
    clock.now += 60
    engine._tick()
    assert rig.stream.closed
    before = rig.refreshes
    engine.play()
    assert rig.refreshes == before + 1
    assert len(rig.streams) == 2
    assert rig.stream.active


# -- golden renders ----------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _golden() -> dict:
    return json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(_golden()["renders"]))
def test_golden_renders_match(rig, clock, name):
    manifest = _golden()
    arrays = {}
    for media_id, digest in manifest["media"].items():
        path = GOLDEN / "media" / f"{media_id}.wav"
        assert _sha256(path) == digest, f"{path.name} is not the file the renders used"
        audio, _ = sf.read(path, dtype="float32", always_2d=True)
        arrays[media_id] = np.ascontiguousarray(audio.T)
    reference = GOLDEN / f"{name}.wav"
    assert _sha256(reference) == manifest["renders"][name]["sha256"]
    expected, rate = sf.read(reference, dtype="float32", always_2d=True)
    assert rate == manifest["rate"]
    project = Project.from_json((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    store = MemoryStore(arrays)

    np.testing.assert_allclose(mixer.mix(project, store, 0, len(expected)).T, expected,
                               rtol=0, atol=1e-6)

    # The engine, in uneven blocks, must give the same samples.
    rig.device_rate = float(rate)
    engine = Engine(FakeSession(project, store), background=False, clock=clock)
    engine.play(0)
    blocks, sizes = [], [1000, 333, 1024, 7, 2048]
    while engine.status()["playing"]:
        blocks.append(engine._render(sizes[len(blocks) % len(sizes)]))
    played = np.concatenate(blocks)[: len(expected)]
    np.testing.assert_allclose(played, expected, rtol=0, atol=1e-6)
    assert engine.status()["position"] == manifest["renders"][name]["frames"]


def test_golden_regeneration_refuses_without_the_flag():
    before = {p.name: p.read_bytes() for p in GOLDEN.glob("*.*")}
    run = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(GOLDEN / "regenerate.py")], cwd=ROOT,
        capture_output=True, text=True, check=False)
    assert run.returncode != 0
    assert "--i-changed-the-mixer" in run.stderr
    assert {p.name: p.read_bytes() for p in GOLDEN.glob("*.*")} == before


# -- hardware tests stay out of the default run -------------------------------


def test_hardware_tests_run_only_when_asked_for():
    def collect(*args):
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, "-m", "pytest", "--collect-only", "-q", *args],
            cwd=ROOT, capture_output=True, text=True, check=False).stdout

    assert "test_play.py" not in collect("-p", "no:cacheprovider")
    assert "test_play.py" in collect("tests/hardware/test_play.py",
                                     "-p", "no:cacheprovider")
