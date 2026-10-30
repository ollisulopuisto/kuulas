"""Track effect layers, tier 1 (WP23a first slice): one causal effect, a high-pass.

A layer is a frozen record on a ``Track`` (``model.FxLayer``): kind, cutoff and
bypass, saved with the project. ``FxState`` holds the running filter state per
track and per layer for live playback; the callback only does arithmetic on
the block it is given (no allocation beyond the block, no I/O, no locks).

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
        """``x`` is ``(channels, n)``; returns a new array."""
        b0, b1, b2, a1, a2 = self.coef
        y = np.empty_like(x)
        z1, z2 = self.z1, self.z2
        for i in range(x.shape[1]):
            xi = x[:, i]
            yi = b0 * xi + z1
            z1 = b1 * xi - a1 * yi + z2
            z2 = b2 * xi - a2 * yi
            y[:, i] = yi
        self.z1, self.z2 = z1, z2
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

    def reset(self) -> None:
        self._next.clear()
        self._filters.clear()

    def process(self, track, buf: np.ndarray, first: int) -> np.ndarray:
        """``buf`` ``(2, n)`` float64 of ``track`` at timeline frame ``first``."""
        layers = track.fx
        if not layers:
            return buf
        if self._next.get(track.id) != first:  # not the block that follows: a seek
            for key in [k for k in self._filters if k[0] == track.id]:
                del self._filters[key]
        self._next[track.id] = first + buf.shape[1]
        for index, layer in enumerate(layers):
            key = (track.id, index)
            if layer.bypass or layer.kind != HIGHPASS:
                self._filters.pop(key, None)  # at rest: a later switch-on starts clean
                continue
            sig = (layer.kind, layer.hz)
            held = self._filters.get(key)
            if held is None or held[0] != sig:
                held = (sig, _Biquad(highpass_coefficients(layer.hz, self.rate)))
                self._filters[key] = held
            buf = held[1].run(buf)
        return buf
