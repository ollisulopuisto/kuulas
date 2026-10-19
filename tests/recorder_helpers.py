"""Shared helpers for the kuulas_recorder tests: a fake device spec, a short
socket path, and a supervisor running in this process with real worker
subprocesses on the fake device. No real audio device is ever opened."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from kuulas_recorder.sources import FAKE_ENV, counter_frame, input_devices

RATE = 48000

FAKE_DEVICES = [
    {"index": 0, "name": "Fake Mic", "channels": 2, "default_rate": 48000.0,
     "hostapi": "fake", "default": True},
    {"index": 1, "name": "Slow Mic", "channels": 1, "default_rate": 44100.0,
     "hostapi": "fake", "default": False},
]


class FakeDevice:
    """The spec file the fake worker source and device list read."""

    def __init__(self, path: Path):
        self.path = path
        self.spec = {"devices": FAKE_DEVICES, "epoch_ns": time.monotonic_ns()}
        self.write()

    def write(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.spec))
        tmp.replace(self.path)

    def set(self, **flags) -> None:
        self.spec.update(flags)
        self.write()


def short_dir() -> Path:
    """A folder with a short path: a socket path must stay under 104 bytes."""
    return Path(tempfile.mkdtemp(prefix="kr"))


def remove(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def ints(path) -> np.ndarray:
    data, _ = sf.read(path, dtype="int32")
    return data >> 8


def frame_of(path, i: int = 0, channel: int = 0) -> int:
    """The fake signal's frame number (mod 2**20) at sample ``i`` of a file."""
    return counter_frame(int(ints(path)[i]), channel)


def contiguous(values: np.ndarray, channel: int = 0) -> bool:
    """Every sample is the next frame of the fake counter."""
    frames = (values.astype(np.int64) + (1 << 19) - 1000 * channel) % (1 << 20)
    return bool(np.all(np.diff(frames) % (1 << 20) == 1))


def wait_until(fn, timeout: float = 10.0, every: float = 0.02):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise AssertionError("condition not met in time")


class FakeAwake:
    def __init__(self):
        self.starts = 0
        self.stops = 0
        self.active = False

    def start(self):
        self.starts += 1
        self.active = True

    def stop(self):
        self.stops += 1
        self.active = False


def fake_devices() -> list[dict]:
    return input_devices()


__all__ = ["FAKE_ENV", "RATE"]
