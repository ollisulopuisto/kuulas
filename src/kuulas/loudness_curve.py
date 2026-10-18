"""Short-term loudness over time, per track and for the whole mix (WP49).

Monitoring from analysis, not live metering: the editor draws a thin curve on
each lane against the track's target, and the transport bar reads the
programme's integrated LUFS and true peak. Nothing here runs in the audio
callback.

The numbers come from speechmix's ``IntegratedMeter`` (the meter
``loudness.py`` and the chain already use) and ``chain.true_peak``; this
module only feeds them the project in 60 s chunks and picks the windows.

* **Window:** 3 s (EBU short-term), hop 1 s. A point's time is the *centre* of
  its window, so the curve lines up with what is heard around the playhead.
  A programme shorter than one window has no curve.
* **Silence** reads ``FLOOR_LUFS`` (-70, the BS.1770 absolute gate), never
  -inf: the curve must survive JSON and drawing.
* **Tracks as heard:** each track is its stem with its gain and automation
  (ducking) applied, duplicated to stereo, so a mono track reads what it
  contributes to a stereo mix. Pan, buses and the master are in the mix
  curve only.
* **Cache:** ``caches/analysis/<key>.json``, keyed on the media hashes and on
  every field of the project that can change the sound (``caches.key``). A
  rename or a new target changes no key; a gain change changes that track's
  key and the mix's. A key that cannot be computed means no cache, and every
  recompute is logged.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from speechmix.chain import true_peak
from speechmix.meter import IntegratedMeter

from . import caches, mixer
from .loudness import track_target_lufs
from .messages import t

if TYPE_CHECKING:
    from collections.abc import Callable

    from .model import Project, Track

log = logging.getLogger("kuulas.loudness_curve")

#: Bump when the numbers this module computes change (``caches``).
ALGORITHM = "loudness-curve@1"

WINDOW_SEC = 3.0
HOP_SEC = 1.0
CHUNK_SEC = 60
FLOOR_LUFS = -70.0


@dataclass(frozen=True)
class Measured:
    """``curve`` is ``[(time_seconds, lufs), ...]``."""

    curve: list[tuple[float, float]]
    integrated: float | None
    true_peak_db: float | None

    def to_dict(self) -> dict:
        return {"curve": [[t_, v] for t_, v in self.curve],
                "integrated": self.integrated, "true_peak_db": self.true_peak_db}


class Accumulator:
    """Feed it chunks in order; ``result`` gives the curve. One per curve, so
    a caller can read each chunk of the timeline once and hand it to several."""

    def __init__(self, rate: int):
        self.rate = int(rate)
        self.meter = IntegratedMeter(self.rate)
        self.peak = 0.0

    def add(self, chunk: np.ndarray) -> None:
        self.meter.add(chunk)
        if chunk.size:
            self.peak = max(self.peak, float(true_peak(chunk)))

    def result(self) -> Measured:
        step = self.meter.step_seconds()
        every = max(1, round(HOP_SEC / step))
        values = self.meter.short_term()
        curve = []
        for i in range(0, values.size, every):
            v = float(values[i])
            v = max(v, FLOOR_LUFS) if math.isfinite(v) else FLOOR_LUFS
            curve.append((round(i * step + WINDOW_SEC / 2, 3), round(v, 2)))
        integrated = self.meter.value()
        peak_db = 20.0 * math.log10(self.peak) if self.peak > 0 else None
        return Measured(
            curve,
            None if integrated is None else round(float(integrated), 2),
            None if peak_db is None else round(peak_db, 2))


def measure(read: Callable[[int, int], np.ndarray], frames: int, rate: int) -> Measured:
    """Curve, integrated LUFS and true peak of ``frames`` frames, from
    ``read(first, count) -> (channels, count)``, 60 s at a time."""
    acc = Accumulator(rate)
    step = CHUNK_SEC * rate
    for first in range(0, frames, step):
        acc.add(read(first, min(step, frames - first)))
    return acc.result()


# -- the project ------------------------------------------------------------


def _shas(p: Project, tracks) -> list[str]:
    out = set()
    for track in tracks:
        for clip in track.clips:
            out.add(p.media_item(clip.media).sha256)
    return sorted(out)


def _track_key(p: Project, track: Track) -> str:
    # Name, speaker, kind, bus, mute, solo and the target change no sample of
    # the stem, so they stay out of the key.
    body = {k: v for k, v in track.to_dict().items()
            if k not in ("name", "speaker", "kind", "bus", "mute", "solo",
                         "target_lufs")}
    return caches.key(_shas(p, [track]),
                      {"rate": p.rate, "length": p.length, "track": body,
                       "what": "track"}, ALGORITHM)


def _mix_key(p: Project) -> str:
    tracks = [{k: v for k, v in tr.to_dict().items() if k not in ("name", "target_lufs")}
              for tr in p.tracks]
    return caches.key(_shas(p, p.tracks),
                      {"rate": p.rate, "length": p.length, "tracks": tracks,
                       "buses": [b.to_dict() for b in p.buses],
                       "master": p.master_gain_db, "what": "mix"}, ALGORITHM)


def _load(where: Path | None) -> dict | None:
    if where is None:
        return None
    try:
        return json.loads(where.read_text())
    except (OSError, ValueError):
        return None  # missing, damaged or never written: measure again


def _save(where: Path | None, value: dict) -> None:
    if where is None:
        return
    try:
        caches.write_atomic(where, lambda f: f.write(json.dumps(value).encode()))
    except OSError:
        log.warning(t("log.cache.recompute", kind="loudness (not saved)",
                      media_id=where.stem[:12]))


def _where(root, key_fn, what: str) -> tuple[Path | None, str | None]:
    """``(cache file, key)``; ``(None, None)`` when there is no cache folder or
    the key cannot be computed (fail closed: measure, do not trust)."""
    if root is None:
        return None, None
    try:
        k = key_fn()
    except caches.CacheKeyError:
        log.warning(t("log.cache.no_key", kind="loudness", media_id=what))
        return None, None
    return caches.path(root, "analysis", k, "json"), k


def project_curves(p: Project, store: mixer.Store,
                   cache_root: str | Path | None = None) -> dict:
    """``{"tracks": [{"track_id", "curve", "integrated", "true_peak_db"}],
    "mix": {"curve", "integrated", "true_peak_db"}}`` for the timeline
    ``[0, p.length)``. Takes a snapshot ``Project``: the caller does not hold
    the session lock while this runs. Tracks without clips are left out.

    A track's ``integrated`` is BS.1770 gated, over the stem as heard: gated
    stretches and muted clips are silence in the stem, and the gate leaves
    silence out, so they do not count. The track's own mute switch is not
    applied (a muted track still reads what it would contribute)."""
    tracks = [tr for tr in p.tracks if tr.clips]
    wanted: list[tuple[str, Track | None]] = [(tr.id, tr) for tr in tracks]
    wanted.append(("", None))  # the mix
    results: dict[str, dict] = {}
    pending: dict[str, tuple[Accumulator, Path | None]] = {}
    for ident, track in wanted:
        where, _ = _where(cache_root, (lambda tr=track: _track_key(p, tr)) if track
                          else (lambda: _mix_key(p)), ident or "mix")
        hit = _load(where)
        if hit is not None:
            results[ident] = hit
            continue
        if where is not None:
            log.info(t("log.cache.recompute", kind="loudness", media_id=ident or "mix"))
        pending[ident] = (Accumulator(p.rate), where)

    step = CHUNK_SEC * p.rate
    by_id = {tr.id: tr for tr in tracks}
    channels = {tr.id: 1 if tr.mono else
                max(1, min(2, max(p.media_item(c.media).channels for c in tr.clips)))
                for tr in tracks}
    for first in range(0, p.length if pending else 0, step):
        count = min(step, p.length - first)
        for ident, (acc, _) in pending.items():
            if ident:
                chunk = mixer.track_stem(by_id[ident], store, first, count,
                                         channels[ident], as_heard=True, rate=p.rate)
            else:
                chunk = mixer.mix(p, store, first, count)
            acc.add(chunk)
    for ident, (acc, where) in pending.items():
        results[ident] = acc.result().to_dict()
        _save(where, results[ident])

    # The target is edit state that changes no sample, so it is added here and
    # never cached: setting one costs no remeasure. The readout in the track
    # header (own target, else the role's) is this number against "integrated".
    return {"tracks": [{"track_id": tr.id, **results[tr.id],
                        "target_lufs": track_target_lufs(tr)} for tr in tracks],
            "mix": results[""]}
