"""Who is speaking when every mic hears everybody: a relative decision (pure).

``floor + margin`` per track asks "is this mic above its own noise?". In a
room where every mic picks up everybody's speech all the time that is always
yes. The question that works is relative: mic ``i`` is the active one only
when its level, corrected for how much it normally leaks of mic ``j``, beats
``j``.

* ``estimate_offsets``: per ordered pair (i hears j) the typical level
  difference ``db_i - db_j`` (a negative number: the bleed) over the hops
  where the ground truth says ``i`` is muted while ``j`` is open and
  speaking. The ground truth is the owner's hand mutes in the first minutes.
* ``speaking``: ``i`` is speaking in a hop when it is above its own floor
  by ``presence_db`` and ``db_i - db_j - offset_ij > margin_db`` for every
  other mic ``j`` that is itself present. Two people talking at once: both
  pass (each beats the other's bleed of them); one talking: only that mic.

Arrays are ``(mics, hops)`` in dB. No audio, no project, no speechmix: the
caller (``analysis``) measures, applies the usual closing of gaps and the
look-ahead, and merges. Experimental: an option of Auto-Silence only for a
project that has hand mutes to calibrate from.
"""

from __future__ import annotations

import numpy as np

#: A mic's floor is this percentile of its valid hops (silence is most of a
#: mic's time in a conversation).
FLOOR_PERCENTILE = 10.0
#: A mic counts as "speaking" for calibration when this far over its floor.
CALIBRATION_ACTIVE_DB = 12.0
#: Fewest hops (1 s at 20 ms) a pair needs to have its own offset.
MIN_PAIR_HOPS = 50
#: How far a mic's corrected level must beat the other's to be the active one.
RELATIVE_MARGIN_DB = 3.0
#: Used for a pair with too little evidence when no pair has any (speechmix
#: measured the median bleed 12.8 dB below the speaker).
FALLBACK_OFFSET_DB = -12.8


def floors(db: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Per mic noise floor, dB."""
    out = np.full(db.shape[0], -120.0)
    for i in range(db.shape[0]):
        if valid[i].any():
            out[i] = float(np.percentile(db[i][valid[i]], FLOOR_PERCENTILE))
    return out


def estimate_offsets(db: np.ndarray, valid: np.ndarray, muted: np.ndarray,
                     window: np.ndarray | None = None) -> np.ndarray:
    """``offsets[i, j]``: the median of ``db_i - db_j`` over hops in the
    calibration ``window`` (bool per hop; everything when None) where mic
    ``i`` is muted, ``j`` is not and is clearly speaking. A pair with fewer
    than ``MIN_PAIR_HOPS`` such hops gets the median of the pairs that have
    enough (``FALLBACK_OFFSET_DB`` when none has). The diagonal is 0."""
    n = db.shape[0]
    floor = floors(db, valid)
    use = np.ones(db.shape[1], dtype=bool) if window is None else np.asarray(window, bool)
    out = np.full((n, n), np.nan)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            hops = (use & valid[i] & valid[j] & muted[i] & ~muted[j]
                    & (db[j] > floor[j] + CALIBRATION_ACTIVE_DB))
            if int(hops.sum()) >= MIN_PAIR_HOPS:
                out[i, j] = float(np.median(db[i][hops] - db[j][hops]))
    known = out[np.isfinite(out)]
    fill = float(np.median(known)) if known.size else FALLBACK_OFFSET_DB
    out = np.where(np.isnan(out), fill, out)
    np.fill_diagonal(out, 0.0)
    return out


def speaking(db: np.ndarray, valid: np.ndarray, offsets: np.ndarray,
             presence_db: float, margin_db: float = RELATIVE_MARGIN_DB) -> np.ndarray:
    """``(mics, hops)`` bool: who is speaking in each hop (see the module doc).
    Hops outside ``valid`` are False."""
    n = db.shape[0]
    floor = floors(db, valid)
    present = valid & (db > floor[:, None] + presence_db)
    on = present.copy()
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            beaten = (db[i] - db[j] - offsets[i, j]) <= margin_db
            # A mic that is not itself present cannot beat anybody; one that
            # is absent from the grid (not valid) is no rival either.
            on[i] &= ~(beaten & present[j])
    return on
