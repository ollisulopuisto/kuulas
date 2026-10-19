"""kuulas_recorder.capture: callback, ring and writer, with a fake device.

No real audio device: ``FakeSource`` calls the block callback from the test.
"""

import errno
import gc
import os
import time
import tracemalloc

import numpy as np
import pytest
import soundfile as sf

from kuulas_recorder import wavfile
from kuulas_recorder.capture import Capture, Ring
from kuulas_recorder.sources import FakeSource, SourceError, counter_frame

RATE = 48000
BLOCK = 1024


def ints(path) -> np.ndarray:
    data, _ = sf.read(path, dtype="int32")
    return data >> 8


def expected(first: int, n: int, channel: int) -> np.ndarray:
    frames = np.arange(first, first + n, dtype=np.int64)
    return (frames + 1000 * channel) % (1 << 20) - (1 << 19)


class Events(list):
    def __call__(self, ev):
        self.append(ev)

    def of(self, kind):
        return [e for e in self if e["ev"] == kind]


def capture(tmp_path, source, **kw):
    events = Events()
    kw.setdefault("channels", [1])
    kw.setdefault("names", ["Olli"])
    c = Capture(source, folder=tmp_path, take="t1", report=events, rate=RATE,
                blocksize=BLOCK, **kw)
    return c, events


def test_take_writes_one_file_per_channel_with_the_right_samples(tmp_path):
    src = FakeSource(channels=3, blocksize=BLOCK)
    c, events = capture(tmp_path, src, channels=[3, 1], names=["Guest", "Host"])
    c.start()
    src.emit(50)
    c.stop()
    n = 50 * BLOCK
    guest, host = tmp_path / "t1-Guest.wav", tmp_path / "t1-Host.wav"
    assert np.array_equal(ints(guest), expected(0, n, 2))
    assert np.array_equal(ints(host), expected(0, n, 0))
    assert events.of("opened")[0]["files"] == {"Guest": guest.name, "Host": host.name}
    assert events.of("closed")[-1]["frames"] == {"Guest": n, "Host": n}


def test_files_are_valid_at_every_flush_while_recording(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = capture(tmp_path, src, flush_seconds=0.1)
    c.start()
    path = tmp_path / "t1-Olli.wav"
    for _ in range(10):
        src.emit(10)
        assert c.wait_drained()
        flushed = events.of("flushed")
        assert flushed
        on_disk = flushed[-1]["frames"]["Olli"]
        # The writer may flush again while this reads: one read, checked alone.
        got = ints(path)
        assert len(got) >= on_disk
        assert np.array_equal(got, expected(0, len(got), 0))
    c.stop()


def test_flush_happens_on_the_wall_clock_when_audio_trickles(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = capture(tmp_path, src, flush_seconds=0.05)
    c.start()
    src.emit(1)  # far less than 0.05 s of audio
    time.sleep(0.3)
    assert events.of("flushed")
    assert sf.info(tmp_path / "t1-Olli.wav").frames == BLOCK
    c.stop()


def test_first_block_reports_the_recording_clock(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = capture(tmp_path, src)
    c.start()
    before = time.monotonic_ns()
    src.emit(1)
    c.stop()
    first = events.of("first_block")[0]
    # The first frame was captured one block before the block arrived.
    assert before - BLOCK * 1e9 / RATE - 5e6 <= first["mono_ns"] <= before + 5e6
    assert abs(first["utc_ns"] - time.time_ns()) < 5e9


def test_overflow_is_counted(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = capture(tmp_path, src)
    c.start()
    src.emit(3)
    src.emit(2, overflow=True)
    src.emit(3)
    c.stop()
    assert c.ring.overflows == 2
    assert events.of("overflow")[0]["at"] == 3 * BLOCK
    assert events.of("flushed")[-1]["overflows"] == 2


def test_a_full_ring_drops_into_silence_that_keeps_the_clock(tmp_path):
    ring = Ring(slots=4, blocksize=8, channels=1)
    block = np.ones((8, 1), np.float32)
    for _ in range(6):  # nobody reads: two blocks do not fit
        ring.push(block, 8, False)
    assert (ring.written, ring.dropped_frames) == (4, 16)
    ring.read = 4  # the writer catches up
    ring.push(block, 8, False)
    assert ring.silence_before[4 % 4] == 16


def test_writer_stall_becomes_silence_not_a_shift(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = capture(tmp_path, src, ring_seconds=0.05)  # 4 slots
    c.start()
    src.emit(2)
    assert c.wait_drained()
    real_write = os.write
    gate = {"open": False}

    def slow_write(fd, data):
        while not gate["open"]:
            time.sleep(0.001)
        return real_write(fd, data)

    os.write = slow_write
    try:
        src.emit(10)  # the writer is stuck: the ring fills, the rest drops
        gate["open"] = True
        assert c.wait_drained()
    finally:
        os.write = real_write
    src.emit(2)
    c.stop()
    total = 14 * BLOCK
    got = ints(tmp_path / "t1-Olli.wav")
    assert len(got) == total  # same length as the time that passed
    dropout = events.of("dropout")[0]
    lo, hi = dropout["at"], dropout["at"] + dropout["frames"]
    assert np.all(got[lo:hi] == 0)
    assert np.array_equal(got[hi:], expected(hi, total - hi, 0))


def test_size_limit_continues_in_the_next_numbered_file_without_a_lost_frame(tmp_path):
    src = FakeSource(channels=2, blocksize=BLOCK)
    limit = 3 * (2500)  # 2500 frames per file
    c, events = capture(tmp_path, src, channels=[1, 2], names=["A", "B"],
                        max_data_bytes=limit)
    c.start()
    src.emit(6)  # 6144 frames: 2500 + 2500 + 1144
    c.stop()
    for ch, name in enumerate(["A", "B"]):
        parts = [tmp_path / f"t1-{name}.wav", tmp_path / f"t1-{name}~2.wav",
                 tmp_path / f"t1-{name}~3.wav"]
        joined = np.concatenate([ints(p) for p in parts])
        assert [sf.info(p).frames for p in parts] == [2500, 2500, 1144]
        assert np.array_equal(joined, expected(0, 6 * BLOCK, ch))
    opened = events.of("opened")
    assert [(o["segment"], o["continues"]) for o in opened] == [
        (1, False), (2, True), (3, True)]


def test_full_disk_stops_with_everything_written_flushed(tmp_path, monkeypatch):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = capture(tmp_path, src)
    c.start()
    src.emit(5)
    assert c.wait_drained()
    fd = c.files[0].fileno()
    real_write = os.write

    def full(f, data):
        if f == fd:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_write(f, data)

    monkeypatch.setattr(os, "write", full)
    src.emit(3)
    deadline = time.monotonic() + 5
    while c.poll() != "error" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert c.poll() == "error"
    assert c.error[0] == "disk_full"
    monkeypatch.undo()
    c.stop()
    assert events.of("error")[0]["key"] == "disk_full"
    path = tmp_path / "t1-Olli.wav"
    assert sf.info(path).frames == 5 * BLOCK  # every block before the error, readable
    assert np.array_equal(ints(path), expected(0, 5 * BLOCK, 0))


def test_device_loss_is_reported_by_the_source(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, _ = capture(tmp_path, src)
    c.start()
    src.emit(2)
    assert c.poll() is None
    src.lose("unplugged")
    assert c.poll() == "device_lost"
    assert c.lost_reason == "unplugged"
    c.stop()
    assert sf.info(tmp_path / "t1-Olli.wav").frames == 2 * BLOCK


def test_device_loss_is_noticed_when_callbacks_stop(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, _ = capture(tmp_path, src)
    c.start()
    src.emit(1)
    last = c.ring.last_ns
    assert c.poll(last + int(0.5e9)) is None
    assert c.poll(last + int(1.5e9)) == "device_lost"
    assert c.lost_reason == "callbacks_stopped"
    c.stop()


def test_a_device_that_never_delivers_counts_as_lost(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, _ = capture(tmp_path, src)
    c.start()
    assert c.poll(c.started_ns + int(6e9)) == "device_lost"
    c.stop()


def test_refused_device_leaves_no_files(tmp_path):
    src = FakeSource(channels=1, device_rate=44100)
    c, _ = capture(tmp_path, src)
    with pytest.raises(SourceError) as e:
        c.start()
    assert e.value.key == "device_rate_mismatch"
    assert "44100 Hz" in e.value.text
    assert list(tmp_path.iterdir()) == []


def test_existing_take_file_is_never_overwritten(tmp_path):
    (tmp_path / "t1-Olli.wav").write_bytes(b"older take")
    src = FakeSource(channels=1)
    c, _ = capture(tmp_path, src)
    with pytest.raises(FileExistsError):
        c.start()
    assert (tmp_path / "t1-Olli.wav").read_bytes() == b"older take"
    assert not src.started


def test_levels_report_the_peak_per_channel(tmp_path):
    src = FakeSource(channels=2, blocksize=BLOCK)
    c, events = capture(tmp_path, src, channels=[1, 2], names=["A", "B"],
                        level_seconds=BLOCK / RATE)
    c.start()
    src.emit(1)
    c.stop()
    peaks = events.of("levels")[0]["peaks"]
    assert len(peaks) == 2
    assert 0 < peaks[0] <= 0.0625  # the counter signal stays within 2**19 / 2**23


def test_the_fake_signal_numbers_its_frames():
    src = FakeSource(channels=2)
    got = []
    src.start(lambda b, n, o: got.append(b.copy()), lambda w: None)
    src.emit(1)
    v = round(float(got[0][5, 1]) * (1 << 23))
    assert counter_frame(v, channel=1) == 5


class NullWav:
    """A ProgressiveWav that keeps nothing: for hours of audio without the disk."""

    def __init__(self, path, rate, *, max_data_bytes=wavfile.MAX_DATA_BYTES):
        self.path = path
        self.rate = rate
        self.max_data_bytes = max_data_bytes
        self.data_bytes = 0

    frames = property(lambda self: self.data_bytes // 3)
    flushed_frames = frames

    def room_frames(self):
        return (self.max_data_bytes - self.data_bytes) // 3

    def write(self, pcm):
        self.data_bytes += len(pcm)

    def flush(self):
        pass

    def close(self):
        pass

    def abandon(self):
        pass


def test_hours_of_audio_run_in_bounded_memory(tmp_path):
    """Three hours at 48 kHz through callback, ring and writer, as fast as the
    machine goes; memory after the first ten minutes must not grow."""
    block = 16384
    src = FakeSource(channels=1, blocksize=block)
    kept = []

    def report(ev):  # what the worker does: keep nothing but counters
        if ev["ev"] in ("opened", "closed", "error"):
            kept.append(ev)

    c = Capture(src, folder=tmp_path, take="long", channels=[1], names=["A"],
                rate=RATE, blocksize=block, report=report, opener=NullWav,
                poll_seconds=0.0002)
    c.start()
    ten_minutes = 10 * 60 * RATE // block
    three_hours = 3 * 3600 * RATE // block
    for i in range(ten_minutes):
        src.emit(1)
        if i % 16 == 0:  # the ring holds 20 s: 58 blocks of this size
            c.wait_drained()
    c.wait_drained()
    gc.collect()
    tracemalloc.start()
    base, _ = tracemalloc.get_traced_memory()
    for i in range(three_hours - ten_minutes):
        src.emit(1)
        if i % 16 == 0:  # the ring holds 20 s: 58 blocks of this size
            c.wait_drained()
    c.wait_drained()
    gc.collect()
    now, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    c.stop()
    assert now - base < 256 * 1024, f"grew {now - base} bytes"
    assert c.total_frames == three_hours * block
    assert c.ring.dropped_frames == 0
    # Three hours fit in one file (the 4 GB limit is at 8.2 hours).
    assert [e["ev"] for e in kept] == ["opened", "closed"]
