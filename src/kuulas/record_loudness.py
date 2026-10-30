"""Read-only input LUFS from flushed take files, never from the recorder callback."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

from . import priority
from . import record_take as rt
from .meter import ShortTermAccumulator

STALE_SECONDS = 2.5
MAX_SIDECAR_BYTES = 4 * 1024 * 1024
log = logging.getLogger(__name__)


@dataclass
class _Channel:
    meter: ShortTermAccumulator
    end: int | None = None
    value: float | None = None
    last_data: float | None = None
    failed: bool = False


class RecordingLoudnessReader:
    """Per-input BS.1770 windows, with at most four seconds of catch-up."""

    def __init__(self):
        self.key = None
        self.channels: dict[str, _Channel] = {}

    def read(
        self,
        folder: Path,
        take: str,
        rate: int,
        names: list[str],
        *,
        now: float | None = None,
    ) -> list[float | None]:
        now = time.monotonic() if now is None else now
        key = (str(folder), take, rate, tuple(names))
        if key != self.key:
            self.key, self.channels = key, {}
        if rate <= 0:
            return [None] * len(names)
        try:
            with rt.take_path(folder, take, ".take.json").open("rb") as source:
                raw = source.read(MAX_SIDECAR_BYTES + 1)
            if len(raw) > MAX_SIDECAR_BYTES:
                return [None] * len(names)
            data = json.loads(raw)
            segments = data.get("segments", []) if isinstance(data, dict) else []
        except (OSError, ValueError):
            return [None] * len(names)
        result = []
        for name in names:
            state = self.channels.get(name)
            if state is None:
                state = self.channels[name] = _Channel(ShortTermAccumulator(rate))
            try:
                self._read_channel(state, folder, take, name, segments, rate, now)
                state.failed = False
            except (OSError, ValueError, RuntimeError, TypeError, OverflowError) as error:
                # A partial header or missing file never affects capture.
                # Polling runs four times a second: keep one traceback until recovery.
                if not state.failed:
                    log.warning("Recording input loudness unavailable for take %s, "
                                "channel %s: %s", take, name, error, exc_info=True)
                state.failed = True
                state.value = None
            fresh = state.last_data is not None and now - state.last_data <= STALE_SECONDS
            result.append(state.value if fresh else None)
        return result

    @staticmethod
    def _read_channel(state, folder, take, name, segments, rate, now):
        spans = []
        for segment in segments:
            if not isinstance(segment, dict) or segment.get("start_frame") is None:
                continue
            item = (segment.get("files") or {}).get(name)
            if not isinstance(item, dict):
                continue
            filename = item.get("file")
            if (
                not isinstance(filename, str)
                or Path(filename).name != filename
                or not filename.startswith(take + "-")
                or not filename.endswith(".wav")
            ):
                continue
            path = rt.take_path(folder, take, filename[len(take) :])
            start, frames = int(segment["start_frame"]), int(item.get("frames", 0))
            if start >= 0 and frames > 0:
                spans.append((start, frames, path))
        if not spans:
            state.value = None
            return
        latest = max(start + frames for start, frames, _path in spans)
        if state.end is None or latest - state.end > 4 * rate:
            state.meter = ShortTermAccumulator(rate)
            state.value = None
            state.end = max(0, latest - 4 * rate)
        for start, frames, path in sorted(spans):
            if start + frames <= state.end:
                continue
            if start > state.end:
                state.meter = ShortTermAccumulator(rate)
                state.value, state.end = None, start  # restart/gap: no false continuity
            with sf.SoundFile(path) as source:
                if source.channels != 1 or source.samplerate != rate:
                    state.value = None
                    continue
                end = min(frames, len(source))  # never read beyond the flushed WAV header
                offset = max(0, state.end - start)
                if offset >= end:
                    continue
                source.seek(offset)
                while source.tell() < end:
                    block = source.read(
                        min(rate, end - source.tell()), dtype="float32", always_2d=True
                    )
                    if not len(block):
                        break
                    state.value = state.meter.add(block)
                    state.end = start + source.tell()
                    state.last_data = now


class RecordingLoudness:
    """One low-priority reader per editor; capture and history stay untouched."""

    def __init__(self, *, enabled: bool = True):
        self.enabled = enabled
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._request = None
        self._values: list[float | None] = []

    def observe(self, folder: Path, take: str, rate: int, names: list[str]) -> None:
        if not self.enabled or self._stop.is_set():
            return
        request = (folder, take, rate, tuple(names))
        with self._lock:
            if request != self._request:
                self._request = request
                self._values = [None] * len(names)
            if self._thread is None:
                self._thread = priority.thread(self._run, "kuulas-record-lufs")
                self._thread.start()

    def read(self) -> list[float | None]:
        with self._lock:
            return list(self._values)

    def reset(self) -> None:
        with self._lock:
            self._request, self._values = None, []

    def close(self) -> None:
        self._stop.set()
        self.reset()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def _run(self) -> None:
        reader = RecordingLoudnessReader()
        while not self._stop.wait(0.25):
            with self._lock:
                request = self._request
            if request is None:
                reader = RecordingLoudnessReader()
                continue
            folder, take, rate, names = request
            values = reader.read(folder, take, rate, list(names))
            with self._lock:
                if self._request == request:
                    self._values = values
