"""Track effect layers, tier 1 (WP23a first slice): one causal effect, a high-pass.

A layer is a frozen record on a ``Track`` (``model.FxLayer``): kind, cutoff and
bypass, saved with the project. ``FxState`` holds the running filter state per
track and per layer for live playback. NOT real-time ready: callback timing is
unprofiled. Filters are built off the callback by ``FxState.prepare`` (called
from ``Engine.set_project``), and the per-block loop uses plain Python floats,
not per-sample NumPy arrays, but it is NOT allocation-free (each block builds Python
lists via .tolist() and a result list per channel) and it is still a Python loop over
every sample
and every layer, and an unprepared track falls back to building its filter on
the first block. Acceptance needs a native callback timing profile.

Configuration: ``ops.set_track(fx=[...])`` is the only route today. There is no
UI to add or edit a layer, so this is not a user-ready interactive effect.

State rules:
- Blocks must arrive in order. If a block does not start where the last one
  ended (a seek, a loop wrap, a different run), the state resets: the filter
  starts from silence, which is what a fresh offline render does at frame 0.
- A bypassed layer returns the dry signal and keeps its state at rest, so
  turning it on later starts clean.
- Block size does not change the output: processing a signal in any split
  gives the same samples as processing it whole (``process_whole``).

Latency: a biquad high-pass adds no latency of its own. Plugin latency
compensation is NOT done here (needs its own impulse-alignment test first).
"""

from __future__ import annotations

import math

import numpy as np

HIGHPASS = "highpass"
KINDS = (HIGHPASS,)
MIN_HZ, MAX_HZ = 20.0, 400.0
Q = 1.0 / math.sqrt(2.0)  # Butterworth


def highpass_coefficients(hz: float, rate: int) -> tuple[float, ...]:
    """RBJ high-pass biquad ``(b0, b1, b2, a1, a2)`` with a0 divided out."""
    w = 2.0 * math.pi * hz / rate
    alpha = math.sin(w) / (2.0 * Q)
    cw = math.cos(w)
    a0 = 1.0 + alpha
    return ((1.0 + cw) / 2.0 / a0, -(1.0 + cw) / a0, (1.0 + cw) / 2.0 / a0,
            -2.0 * cw / a0, (1.0 - alpha) / a0)


class _Biquad:
    """Transposed direct form II, float64, one state pair per channel."""

    __slots__ = ("coef", "z1", "z2")

    def __init__(self, coef, channels: int = 2):
        self.coef = coef
        self.z1 = np.zeros(channels)
        self.z2 = np.zeros(channels)

    def reset(self) -> None:
        self.z1[:] = 0.0
        self.z2[:] = 0.0

    def run(self, x: np.ndarray) -> np.ndarray:
        """``x`` is ``(channels, n)``; returns a new array. Scalar float math
        per channel: no per-sample array, but it allocates per-block lists."""
        b0, b1, b2, a1, a2 = self.coef
        y = np.empty_like(x)
        for c in range(x.shape[0]):
            z1 = float(self.z1[c])
            z2 = float(self.z2[c])
            xs = x[c].tolist()
            ys = [0.0] * len(xs)
            for i, xi in enumerate(xs):
                yi = b0 * xi + z1
                z1 = b1 * xi - a1 * yi + z2
                z2 = b2 * xi - a2 * yi
                ys[i] = yi
            y[c] = ys
            self.z1[c] = z1
            self.z2[c] = z2
        return y


def process_whole(layer, signal: np.ndarray, rate: int) -> np.ndarray:
    """The reference: ``signal`` ``(channels, n)`` through ``layer`` in one go."""
    if layer.bypass or layer.kind != HIGHPASS:
        return signal
    return _Biquad(highpass_coefficients(layer.hz, rate), signal.shape[0]).run(
        np.asarray(signal, dtype=np.float64))


class FxState:
    """Running state of every layer of every track, for one playing run."""

    def __init__(self, rate: int):
        self.rate = rate
        self._next: dict[str, int] = {}
        self._filters: dict[tuple[str, int], tuple[tuple, _Biquad]] = {}

    def prepare(self, project) -> None:
        """Build the filters of ``project`` off the audio callback (control
        thread). The new table replaces the old one in one assignment; state of
        an unchanged layer is kept, so an edit elsewhere does not click."""
        old = self._filters
        new: dict[tuple[str, int], tuple[tuple, _Biquad]] = {}
        for track in project.tracks:
            for index, layer in enumerate(track.fx):
                if layer.bypass or layer.kind != HIGHPASS:
                    continue
                key = (track.id, index)
                sig = (layer.kind, layer.hz)
                held = old.get(key)
                if held is None or held[0] != sig:
                    held = (sig, _Biquad(highpass_coefficients(layer.hz, self.rate)))
                new[key] = held
        self._filters = new

    def reset(self) -> None:
        self._next.clear()
        for _sig, filt in list(self._filters.values()):
            filt.reset()

    def process(self, track, buf: np.ndarray, first: int) -> np.ndarray:
        """``buf`` ``(2, n)`` float64 of ``track`` at timeline frame ``first``."""
        layers = track.fx
        if not layers:
            return buf
        if self._next.get(track.id) != first:  # not the block that follows: a seek
            for key, (_sig, filt) in list(self._filters.items()):
                if key[0] == track.id:
                    filt.reset()
        self._next[track.id] = first + buf.shape[1]
        for index, layer in enumerate(layers):
            key = (track.id, index)
            if layer.bypass or layer.kind != HIGHPASS:
                held = self._filters.get(key)
                if held is not None:  # at rest: a later switch-on starts clean
                    held[1].reset()
                continue
            sig = (layer.kind, layer.hz)
            held = self._filters.get(key)
            if held is None or held[0] != sig:
                held = (sig, _Biquad(highpass_coefficients(layer.hz, self.rate)))
                self._filters[key] = held
            buf = held[1].run(buf)
        return buf
