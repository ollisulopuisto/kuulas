"""Audio sources: the real input device, and fakes for tests.

The capture engine only sees ``AudioSource``: it is started with a block
callback and a "device lost" callback and stopped. ``SoundDeviceSource`` is the
real one (``sounddevice.InputStream``, CoreAudio on the Mac); ``FakeSource`` is
driven block by block from a test; ``ThreadedFakeSource`` runs in a worker
process when ``KUULAS_RECORDER_FAKE`` names a fake spec file (tests only; see
docs/RECORDER.md).

``sounddevice`` is imported only inside the functions that open a real device,
so the supervisor and fake workers never load PortAudio.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import numpy as np

# A block of float32 audio (frames x channels), its frame count, and whether
# the host reported an input overflow (audio lost before it reached us).
BlockCallback = Callable[[np.ndarray, int, bool], None]
LostCallback = Callable[[str], None]

FAKE_ENV = "KUULAS_RECORDER_FAKE"


class SourceError(Exception):
    """An input that cannot be opened, with a stable ``key`` and a plain text."""

    def __init__(self, key: str, text: str):
        super().__init__(text)
        self.key = key
        self.text = text


class AudioSource(Protocol):
    def start(self, on_block: BlockCallback, on_lost: LostCallback) -> None: ...
    def stop(self) -> None: ...
    def describe(self) -> dict: ...


def check_rate(name: str, device_rate: float, rate: int) -> None:
    """Refuse a device that does not run at the project rate: never resample live."""
    if round(device_rate) != rate:
        raise SourceError(
            "device_rate_mismatch",
            f"{name} runs at {round(device_rate)} Hz, not {rate} Hz. Set it to {rate} Hz "
            "in Audio MIDI Setup (or the device's own settings) and start again; the "
            "recorder never resamples while recording.")


def resolve_device(devices: list[dict], want: object) -> dict:
    """The input device ``want`` names: an index, a name, ``{"index", "name"}`` or
    ``None`` for the default input. A name wins over an index, because indexes
    change when a device is unplugged and plugged back in."""
    index = name = None
    if isinstance(want, dict):
        index, name = want.get("index"), want.get("name")
    elif isinstance(want, bool):
        index = None
    elif isinstance(want, int):
        index = want
    elif isinstance(want, str):
        name = want
    if name is not None:
        for d in devices:
            if d["name"] == name and (index is None or d["index"] == index):
                return d
        for d in devices:
            if d["name"] == name:
                return d
        raise SourceError("device_not_found", f"No input device named {name!r}.")
    if index is not None:
        for d in devices:
            if d["index"] == index:
                return d
        raise SourceError("device_not_found", f"No input device number {index}.")
    for d in devices:
        if d.get("default"):
            return d
    raise SourceError("device_not_found", "There is no default input device.")


def input_devices() -> list[dict]:
    """Input devices: ``{index, name, channels, default_rate, hostapi, default}``.

    PortAudio reads the device list once when it starts, so a long-running
    process does not see devices plugged in later; the supervisor asks a fresh
    process (``kuulas-recorder devices --json``) each time for that reason.
    """
    spec = fake_spec()
    if spec is not None:
        return [] if spec.get("unplugged") else [dict(d) for d in spec["devices"]]
    import sounddevice as sd  # noqa: PLC0415 - PortAudio only where a device is used

    default_in = sd.default.device[0]
    apis = sd.query_hostapis()
    out = []
    for d in sd.query_devices():
        if d["max_input_channels"] <= 0:
            continue
        out.append({
            "index": d["index"],
            "name": d["name"],
            "channels": d["max_input_channels"],
            "default_rate": d["default_samplerate"],
            "hostapi": apis[d["hostapi"]]["name"],
            "default": d["index"] == default_in,
        })
    return out


# --- the real device --------------------------------------------------------------


class SoundDeviceSource:
    """``sounddevice.InputStream`` at the project rate, float32, fixed blocks."""

    def __init__(self, device: object, channels: int, rate: int, blocksize: int):
        self.want = device
        self.channels = channels
        self.rate = rate
        self.blocksize = blocksize
        self.info: dict | None = None
        self._stream = None
        self._stopping = False
        self._on_block: BlockCallback | None = None
        self._on_lost: LostCallback | None = None
        self.callback_errors = 0

    def describe(self) -> dict:
        return dict(self.info or {})

    def _callback(self, indata, frames, _time, status) -> None:
        # The audio thread. Never raises: an exception here would stop the stream.
        try:
            self._on_block(indata, frames, bool(status.input_overflow))  # type: ignore[misc]
        except BaseException:  # noqa: BLE001 - the audio callback must never raise
            self.callback_errors += 1

    def _finished(self) -> None:
        if not self._stopping and self._on_lost is not None:
            self._on_lost("stream_finished")

    def start(self, on_block: BlockCallback, on_lost: LostCallback) -> None:
        import sounddevice as sd  # noqa: PLC0415 - PortAudio only in the worker

        info = resolve_device(input_devices(), self.want)
        if info["channels"] < self.channels:
            raise SourceError(
                "channels_unavailable",
                f"{info['name']} has {info['channels']} input channels; "
                f"channel {self.channels} was asked for.")
        check_rate(info["name"], info["default_rate"], self.rate)
        self.info = info
        self._on_block, self._on_lost = on_block, on_lost
        extra = None
        if info.get("hostapi") == "Core Audio":
            # Belt and braces for check_rate: fail rather than let CoreAudio convert.
            extra = sd.CoreAudioSettings(fail_if_conversion_required=True)
        try:
            self._stream = sd.InputStream(
                device=info["index"], channels=self.channels, samplerate=self.rate,
                dtype="float32", blocksize=self.blocksize,
                # Nothing listens live (owner, 2026-10-19), so trade latency for
                # a deeper host buffer: fewer overflows when Python stalls.
                latency="high", callback=self._callback,
                finished_callback=self._finished, extra_settings=extra)
            self._stream.start()
        except Exception as e:
            raise SourceError("device_open_failed",
                              f"Could not open {info['name']}: {e}") from e

    def stop(self) -> None:
        self._stopping = True
        stream, self._stream = self._stream, None
        if stream is not None:
            with contextlib.suppress(Exception):
                stream.abort()
            with contextlib.suppress(Exception):
                stream.close()


# --- fakes ------------------------------------------------------------------------


def counter_block(first: int, frames: int, channels: int) -> np.ndarray:
    """The fake signal: channel ``c`` at frame ``n`` holds the 24-bit value
    ``(n + 1000 * c) % 2**20 - 2**19``, exact in float32 and in 24-bit PCM, so a
    test can check every sample and see exactly where a gap is."""
    n = np.arange(first, first + frames, dtype=np.int64)[:, None]
    c = np.arange(channels, dtype=np.int64)[None, :]
    ints = (n + 1000 * c) % (1 << 20) - (1 << 19)
    return (ints / float(1 << 23)).astype(np.float32)


def counter_frame(value: int, channel: int = 0) -> int:
    """Invert ``counter_block`` for one sample: the frame number modulo 2**20."""
    return (value + (1 << 19) - 1000 * channel) % (1 << 20)


class FakeSource:
    """A device the test drives: ``emit`` calls the block callback right away."""

    def __init__(self, channels: int, rate: int = 48000, blocksize: int = 1024, *,
                 name: str = "Fake Mic", device_rate: float | None = None,
                 fail_with: SourceError | None = None):
        self.channels = channels
        self.rate = rate
        self.blocksize = blocksize
        self.name = name
        self.device_rate = rate if device_rate is None else device_rate
        self.fail_with = fail_with
        self.frame = 0
        self.started = False
        self._on_block: BlockCallback | None = None
        self._on_lost: LostCallback | None = None
        self._buf = np.zeros((blocksize, channels), np.float32)

    def describe(self) -> dict:
        return {"index": 0, "name": self.name, "channels": self.channels,
                "default_rate": self.device_rate, "hostapi": "fake"}

    def start(self, on_block: BlockCallback, on_lost: LostCallback) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        check_rate(self.name, self.device_rate, self.rate)
        self._on_block, self._on_lost = on_block, on_lost
        self.started = True

    def emit(self, blocks: int = 1, *, overflow: bool = False) -> None:
        for _ in range(blocks):
            if not self.started:
                return
            self._buf[:] = counter_block(self.frame, self.blocksize, self.channels)
            self.frame += self.blocksize
            self._on_block(self._buf, self.blocksize, overflow)  # type: ignore[misc]

    def skip(self, frames: int) -> None:
        """Let time pass without delivering audio (a stall or a host overflow)."""
        self.frame += frames

    def lose(self, why: str = "unplugged") -> None:
        if self._on_lost is not None:
            self._on_lost(why)

    def stop(self) -> None:
        self.started = False


def fake_spec() -> dict | None:
    """The fake spec named by ``KUULAS_RECORDER_FAKE``, or None (a real device)."""
    path = os.environ.get(FAKE_ENV)
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A test is rewriting it; treat as the default fake device.
        return {"devices": [{"index": 0, "name": "Fake Mic", "channels": 2,
                             "default_rate": 48000.0, "hostapi": "fake",
                             "default": True}]}


class ThreadedFakeSource(FakeSource):
    """A fake device in a worker process: delivers blocks in real time from a thread.

    The spec file (JSON) holds ``devices`` (as ``input_devices`` returns them) and
    flags a test may flip while it runs: ``unplugged`` (the device vanishes:
    callbacks stop and it leaves the device list), ``stall`` (callbacks stop
    but the device stays listed), ``overflow`` (every block reports an input
    overflow). The signal is ``counter_block`` numbered from ``epoch_ns`` (a
    ``time.monotonic_ns`` value), so the samples of a later segment show how
    much time really passed.
    """

    def __init__(self, want: object, channels: int, rate: int, blocksize: int,
                 spec_path: str):
        super().__init__(channels, rate, blocksize)
        self.spec_path = spec_path
        self.want = want
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._info: dict = {}

    def describe(self) -> dict:
        return dict(self._info)

    def _spec(self) -> dict:
        return fake_spec() or {}

    def start(self, on_block: BlockCallback, on_lost: LostCallback) -> None:
        info = resolve_device(input_devices(), self.want)
        if info["channels"] < self.channels:
            raise SourceError("channels_unavailable",
                              f"{info['name']} has {info['channels']} input channels.")
        check_rate(info["name"], info["default_rate"], self.rate)
        self._info = info
        self.name = info["name"]
        self.device_rate = info["default_rate"]
        super().start(on_block, on_lost)
        epoch = int(self._spec().get("epoch_ns", time.monotonic_ns()))
        self.frame = max(0, (time.monotonic_ns() - epoch) * self.rate // 1_000_000_000)
        self._thread = threading.Thread(target=self._run, name="fake-audio", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        period = self.blocksize / self.rate
        next_t = time.monotonic() + period
        spec, spec_at = self._spec(), 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now - spec_at > 0.1:
                spec, spec_at = self._spec(), now
            if spec.get("unplugged") or spec.get("stall"):
                self.frame += round((now - (next_t - period)) * self.rate)
                next_t = now + period
                self._stop.wait(period)
                continue
            delay = next_t - now
            if delay > 0:
                self._stop.wait(delay)
            self.emit(1, overflow=bool(spec.get("overflow")))
            next_t += period

    def stop(self) -> None:
        super().stop()
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)


def make_source(device: object, channels: int, rate: int, blocksize: int) -> AudioSource:
    """The source a worker records from: the fake when the env names one."""
    spec_path = os.environ.get(FAKE_ENV)
    if spec_path:
        return ThreadedFakeSource(device, channels, rate, blocksize, spec_path)
    return SoundDeviceSource(device, channels, rate, blocksize)
