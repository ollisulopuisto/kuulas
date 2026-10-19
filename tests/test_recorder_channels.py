"""WP12b: several channels of one device, each to its own file; one channel's trouble
never costs the others their audio. Fake device only."""

import errno
import time

import numpy as np
import soundfile as sf

from kuulas_recorder import names as naming
from kuulas_recorder import wavfile
from kuulas_recorder.capture import Capture
from kuulas_recorder.sources import FakeSource

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


class FlakyWav(wavfile.ProgressiveWav):
    """A file whose writes fail with ``failure`` once it holds ``after`` frames."""

    failure: OSError = OSError(errno.EIO, "Input/output error")
    after = 3 * BLOCK
    only: str | None = "t1-Guest.wav"

    def write(self, pcm):
        mine = self.only is None or self.path.name == self.only
        if mine and self.frames >= self.after:
            raise self.failure
        super().write(pcm)


def capture(tmp_path, source, opener, **kw):
    events = Events()
    c = Capture(source, folder=tmp_path, take="t1", channels=[1, 2],
                names=["Host", "Guest"], report=events, rate=RATE, blocksize=BLOCK,
                opener=opener, **kw)
    return c, events


def test_one_channels_write_error_never_loses_the_other_channels(tmp_path):
    src = FakeSource(channels=2, blocksize=BLOCK)
    c, events = capture(tmp_path, src, FlakyWav)
    c.start()
    src.emit(20)
    assert c.wait_drained()
    c.stop()
    assert c.error is None  # the take goes on
    n = 20 * BLOCK
    assert np.array_equal(ints(tmp_path / "t1-Host.wav"), expected(0, n, 0))
    guest = ints(tmp_path / "t1-Guest.wav")  # a valid whole file, as far as it got
    assert np.array_equal(guest, expected(0, 3 * BLOCK, 1))
    failed = events.of("channel_failed")
    assert [(e["name"], e["at"]) for e in failed] == [("Guest", 3 * BLOCK)]
    assert events.of("closed")[-1]["frames"] == {"Host": n, "Guest": 3 * BLOCK}


def test_a_full_disk_is_still_everyones_problem(tmp_path):
    class Full(FlakyWav):
        failure = OSError(errno.ENOSPC, "No space left on device")

    src = FakeSource(channels=2, blocksize=BLOCK)
    c, _events = capture(tmp_path, src, Full)
    c.start()
    src.emit(20)
    time.sleep(0.3)
    c.stop()
    assert c.error is not None
    assert c.error[0] == "disk_full"


def test_every_channel_failing_ends_the_take_with_an_error(tmp_path):
    class AllBad(FlakyWav):
        only = None

    src = FakeSource(channels=2, blocksize=BLOCK)
    c, _events = capture(tmp_path, src, AllBad)
    c.start()
    src.emit(20)
    time.sleep(0.3)
    c.stop()
    assert c.error is not None
    assert c.error[0] == "write_failed"


def test_channels_of_a_pre_roll_take_stay_in_sync(tmp_path):
    src = FakeSource(channels=2, blocksize=BLOCK)
    events = Events()
    c = Capture(src, folder=None, take=None, channels=[1, 2], names=[], report=events,
                rate=RATE, blocksize=BLOCK, armed=True, preroll_seconds=0.1)
    c.start()
    src.emit(10)
    assert c.wait_drained()
    c.begin(tmp_path, "t1", ["Host", "Guest"])
    deadline = time.monotonic() + 5
    while not c.recording and time.monotonic() < deadline:
        time.sleep(0.01)
    src.emit(10)
    assert c.wait_drained()
    c.stop()
    host, guest = ints(tmp_path / "t1-Host.wav"), ints(tmp_path / "t1-Guest.wav")
    assert len(host) == len(guest) > 10 * BLOCK
    first = (10 * BLOCK) - events.of("preroll")[0]["frames"]
    assert np.array_equal(host, expected(first, len(host), 0))
    assert np.array_equal(guest, expected(first, len(guest), 1))


def test_the_file_name_of_a_channel_is_built_in_one_place():
    assert naming.segment_file("Take 1", "Host", 1) == "Take 1-Host.wav"
    assert naming.segment_file("Take 1", "Host", 2) == "Take 1-Host~2.wav"
