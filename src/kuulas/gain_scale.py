"""Waveform scale from clip, track and envelope gains.

The total gain in dB (clip + track + envelope), the linear scale it maps to,
and linear dB interpolation over a sorted envelope. Pure Python, stdlib only:
no imports from kuulas. Errors are plain ValueError; there is no user-facing
text.
"""

from __future__ import annotations

import itertools
import math

_INF = float("inf")


def total_gain_db(clip_gain_db, track_gain_db, envelope_db=0.0):
    """Return clip + track + envelope gain in dB; None means 0.0.

    ``-inf`` is allowed (silence) and propagates to ``-inf``. Any other
    non-finite input (nan, +inf) raises ``ValueError``.
    """
    gain = 0.0
    for value in (clip_gain_db, track_gain_db, envelope_db):
        if value is None:
            continue
        if math.isnan(value) or value == _INF:
            msg = f"gain value ({value}) must be finite or -inf"
            raise ValueError(msg)
        gain += value
    return gain


def waveform_scale(total_db, max_scale=32.0):
    """Return ``10 ** (total_db / 20)`` capped at ``max_scale``.

    ``-inf`` total gain maps to ``0.0`` (silence).
    """
    if total_db == float("-inf"):
        return 0.0
    return min(10 ** (total_db / 20), max_scale)


def envelope_db_at(envelope, frame):
    """Return the envelope value in dB at ``frame`` by linear interpolation.

    ``envelope`` is a sorted list of ``(frame, db)`` points. The value is held
    flat before the first point and after the last; an empty list or None
    gives 0.0. The input is not mutated.
    """
    if not envelope:
        return 0.0
    points = list(envelope)
    if frame <= points[0][0]:
        return points[0][1]
    if frame >= points[-1][0]:
        return points[-1][1]
    for (f0, db0), (f1, db1) in itertools.pairwise(points):
        if f0 <= frame <= f1:
            if f1 == f0:
                return db1
            return db0 + (db1 - db0) * (frame - f0) / (f1 - f0)
    return points[-1][1]
