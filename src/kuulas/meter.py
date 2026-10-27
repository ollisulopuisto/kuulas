"""The live level meter's arithmetic (owner, 2026-10-19: VU/loudness meters, to get tracks
and buses to unity gain before export).

This shows what plays *now*, measured on the block the audio callback hands to the
device. It is not the loudness readout of a track header (``loudness_curve``: integrated
LUFS from the analysis). Everything here is pure, so the callback only calls
``block_levels``.
"""

from __future__ import annotations

import math

import numpy as np

#: What silence reads, dBFS. A floor, never -inf: the value goes into JSON and a drawing.
FLOOR_DB = -90.0

#: How long the peak-hold tick stays where the peak was, and then how fast it falls (dB
#: per second). 1.5 s and 12 dB/s are the usual DAW feel: long enough to read, gone in
#: about 8 s.
HOLD_S = 1.5
FALL_DB_PER_S = 12.0


def block_levels(block: np.ndarray) -> tuple[float, float, float, float]:
    """``(peak_l, peak_r, mean_square_l, mean_square_r)`` of an ``(frames, 2)`` block.

    Called in the audio callback, so it is a handful of numpy reductions on views: per
    channel one ``abs`` (a block-sized temporary, 8 KB at 2048 frames) with ``max``, and
    one ``dot`` for the mean square. Measured at 2048 frames on the M1 Max, machine
    loaded: about 16 us in all, against a block of 42 ms (``max``/``min`` without
    ``abs`` was no faster; ``einsum`` for the squares was 4x slower than ``dot``).
    """
    frames = block.shape[0]
    if frames == 0:
        return 0.0, 0.0, 0.0, 0.0
    left, right = block[:, 0], block[:, 1]
    return (float(np.abs(left).max()), float(np.abs(right).max()),
            float(np.dot(left, left)) / frames, float(np.dot(right, right)) / frames)


def to_db(linear: float) -> float:
    """dBFS of a linear level (1.0 is full scale). Silence and anything below the floor
    read ``FLOOR_DB``; above full scale it is positive, the clip indicator's cue."""
    if not linear > 0.0:
        return FLOOR_DB
    return max(FLOOR_DB, 20.0 * math.log10(linear))


class PeakHold:
    """A peak-hold tick: it takes a new peak at once, stays for ``hold_s``, then falls at
    ``fall_db_per_s`` but never below the level playing now. Time is passed in (the
    engine's clock), so a test needs no waiting."""

    def __init__(self, hold_s: float = HOLD_S, fall_db_per_s: float = FALL_DB_PER_S):
        self.hold_s = hold_s
        self.fall = fall_db_per_s
        self.held = FLOOR_DB
        self._peaked = 0.0  # when the held value was set
        self._last = 0.0  # the previous update

    def reset(self) -> None:
        self.held = FLOOR_DB
        self._peaked = 0.0
        self._last = 0.0

    def update(self, db: float, now: float) -> float:
        if db >= self.held:
            self.held, self._peaked = db, now
        else:
            # Falling starts when the hold time is over, and is counted from there.
            begin = max(self._last, self._peaked + self.hold_s)
            if now > begin:
                self.held = max(db, self.held - self.fall * (now - begin))
        self._last = now
        return self.held


class ShortTermAccumulator:
    """Bounded live adapter around the podcast pipeline's K-weighted BS.1770 meter.

    Only the last thirty 100 ms powers are needed. Keep the shared filter/tail
    state intact while pruning its integrated-program history, never copy DSP.
    """

    def __init__(self, rate: int):
        from speechmix.meter import IntegratedMeter  # noqa: PLC0415

        self.shared = IntegratedMeter(rate)

    def add(self, block: np.ndarray) -> float | None:
        self.shared.add(block.T)
        self.shared._powers = self.shared._powers[-30:]
        self.shared._speech = self.shared._speech[-30:]
        values = self.shared.short_term()
        if not len(values):
            return None
        value = float(values[-1])
        return max(FLOOR_DB, value) if math.isfinite(value) else FLOOR_DB


class LiveShortTerm:
    """Audio callback only copies into a bounded queue; DSP runs on a worker.

    Sequence gaps (queue overflow), transport changes and rate changes reset
    the three-second window, so a stale reading is never presented as current.
    """

    def __init__(self):
        import threading  # noqa: PLC0415
        from collections import deque  # noqa: PLC0415

        self._pending = deque(maxlen=64)
        self._stop = threading.Event()
        self._worker = None
        self._serial = 0
        self._generation = 0
        self.value = None

    def offer(self, block: np.ndarray, rate: int, run: int) -> None:
        self._serial += 1
        self._pending.append((self._generation, run, rate, self._serial, block.copy()))

    def read(self) -> float | None:
        if self._worker is None and not self._stop.is_set():
            import threading  # noqa: PLC0415

            self._worker = threading.Thread(target=self._run, daemon=True,
                                            name="kuulas-lufs")
            self._worker.start()
        return self.value

    def reset(self) -> None:
        self._generation += 1
        self._pending.clear()
        self.value = None

    def close(self) -> None:
        self.reset()
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=1)

    def _run(self) -> None:
        from .priority import lower_this_thread  # noqa: PLC0415

        lower_this_thread()
        key, serial, accumulator = None, None, None
        while not self._stop.wait(0.02):
            while self._pending and not self._stop.is_set():
                try:
                    generation, run, rate, number, block = self._pending.popleft()
                except IndexError:
                    break  # a concurrent stop cleared the queue
                current = (generation, run, rate)
                try:
                    if current != key or serial is None or number != serial + 1:
                        accumulator = ShortTermAccumulator(rate)
                    value = accumulator.add(block)
                except Exception:  # noqa: BLE001 - a meter failure never stops playback
                    key, serial, accumulator = None, None, None
                    self.value = None
                    continue
                key, serial = current, number
                if generation == self._generation:
                    self.value = value
