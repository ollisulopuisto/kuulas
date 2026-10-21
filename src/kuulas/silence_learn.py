"""Auto-Silence values learned from the clips the user muted by hand (the selection).

The rule is not here: it is the shared podcast package ``silencelearn``
(``calibrate_clips``), the same one podcast-magic and colab-transcribe use, so
an improvement there reaches all three (owner, 2026-10-21: no duplicated code).
This module is the thin adapter (docs/design/SILENCE-LEARN.md):

* ``examples``: the selected clips of speech tracks as ``silencelearn.Clip``,
  in the media file's own seconds (``offset``, not the timeline). A muted clip
  is an example of "closed", an unmuted one of "open". The ``ungated`` flag
  does not change the role: it is a decision about the gate, not about what
  the audio is.
* ``MediaLevels``: the package's ``Levels`` from Kuulas' own level
  measurement (``levels``: the mean square of the channel mean, the same
  number ``analysis.track_levels`` decides on), from the cached per-media
  envelope when the store has one, else from the window's audio alone. Never
  a whole file in memory.
* ``calibrate_tracks``: one ``Calibration`` per selected track, with a code
  the UI translates (the package's own ``reason`` is Finnish prose for its
  log, kept as ``note``).
* ``suggestion``: the learned threshold (absolute dBFS) as the panel's
  Sensitivity, ``margin_db`` over the track's own noise floor, which is what
  the Auto-Silence decision compares with (``grid.lane``).

Pure on the snapshot: ``calibrate_tracks`` is an offload task (the analysis
worker), ``suggestion`` is arithmetic.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable

import numpy as np
import silencelearn as sl
from speechmix import grid
from speechmix.dsp import FLOOR_DB

from . import levels
from .media import streaming
from .model import Project
from .silence_options import RANGES, SilenceOptions

#: Codes of a track's answer (``calibrate_tracks``), translated by the UI as
#: ``ui.silence.learn_<code>``.
LEARNED = "learned"


def examples(p: Project, clip_ids: Iterable[str]) -> dict[str, list[sl.Clip]]:
    """Track id -> the selected clips of that speech track as examples, in track
    and clip order. Clips of music tracks and unknown ids are not examples."""
    wanted = set(clip_ids)
    rate = p.rate
    out: dict[str, list[sl.Clip]] = {}
    for track in p.tracks:
        if track.kind != "speech":
            continue
        found = [sl.Clip(c.media, c.offset / rate, (c.offset + c.length) / rate,
                         muted=c.muted)
                 for c in track.clips if c.id in wanted]
        if found:
            out[track.id] = found
    return out


class MediaLevels:
    """``silencelearn.Levels`` over the project's media (ids as refs, seconds of
    the file). A missing linked file has no level (it would read as digital
    silence, and silence would be learned as the threshold)."""

    def __init__(self, p: Project, store) -> None:
        self.rate = p.rate
        self.store = store
        self.frames = {m.id: m.frames for m in p.media}
        lost = getattr(store, "missing", None)
        self.lost = set(lost()) if callable(lost) else set()
        # The block ``analysis`` asks for, so the envelope is the one already cached.
        self.block = levels.block_frames(round(self.rate * grid.HOP_SEC))
        self._envelopes: dict[str, np.ndarray | None] = {}

    def _envelope(self, ref: str) -> np.ndarray | None:
        if ref not in self._envelopes:
            provider = getattr(self.store, "envelope", None)
            self._envelopes[ref] = None if provider is None else provider(ref, self.block)
        return self._envelopes[ref]

    def level(self, ref: str, start: float, end: float) -> float | None:
        if ref in self.lost or ref not in self.frames:
            return None
        frames = self.frames[ref]
        a = max(0, round(start * self.rate))
        b = min(frames, round(end * self.rate))
        if b <= a:
            return None
        blocks = self._envelope(ref)
        if blocks is not None:
            upto = levels.energy_upto(blocks, self.block, frames, np.array([a, b]))
            mean_sq = float(upto[1] - upto[0]) / (b - a)
        else:
            with streaming():
                audio = self.store.read(ref, a, b - a)
            mono = np.asarray(audio).mean(axis=0, dtype=np.float32).astype(np.float64)
            mean_sq = float(np.mean(np.square(mono)))
        return max(10.0 * math.log10(max(mean_sq, 1e-12)), FLOOR_DB)

    def missing(self) -> bool:
        return bool(self.lost)


def _code(found: sl.Calibration, missing: bool) -> tuple[str, dict]:
    """What the package's answer means, as a code and its numbers."""
    if found.threshold is not None:
        return LEARNED, {}
    if not found.frames:
        if missing:
            return "no_audio", {}
        if found.muted_seconds <= 0:
            return "no_muted", {}
    if found.muted_seconds < sl.MIN_SECONDS:
        return "too_little", {"seconds": round(found.muted_seconds, 1),
                              "min": sl.MIN_SECONDS}
    if found.speech_level is not None:
        return "speech_guard", {"speech": round(found.speech_level, 1)}
    return "no_muted", {}


def calibrate_tracks(p: Project, store, clip_ids: Iterable[str]) -> dict[str, dict]:
    """Track id -> what ``silencelearn.calibrate_clips`` learned from that track's
    selected clips: the ``Calibration``'s fields (JSON-able), ``code`` and
    ``args`` for the UI, ``note`` (the package's own reason)."""
    lv = MediaLevels(p, store)
    out = {}
    for track_id, clips in examples(p, clip_ids).items():
        found = sl.calibrate_clips(clips, lv)
        code, args = _code(found, lv.missing())
        row = dataclasses.asdict(found)
        row.update(code=code, args=args, note=row.pop("reason"),
                   clips=len(clips), muted_clips=sum(c.muted for c in clips))
        out[track_id] = row
    return out


def combined_margin(rows: list[dict]) -> float | None:
    """One margin for every mic (the option is one number): the smallest learned
    one, because closing too much is the worse error (silencelearn's rule)."""
    found = [r["margin_db"] for r in rows if r["code"] == LEARNED
             and r.get("margin_db") is not None]
    return min(found) if found else None


def suggestion(p: Project, calibrations: dict[str, dict], floors: dict[str, float],
               options: SilenceOptions) -> dict:
    """The panel's options with the learned Sensitivity (``margin_db``), and per
    track what was learned or why not: ``{tracks, options, learned, clamped,
    learned_margin_db}``. Everything the clips cannot teach (Closeness, the
    merge and padding times) stays as ``options`` had it."""
    names = {t.id: t.name for t in p.tracks}
    rows = []
    for track_id, cal in calibrations.items():
        row = {"track_id": track_id, "name": names.get(track_id, track_id),
               "floor": floors.get(track_id), "margin_db": None, **cal}
        if row["code"] == LEARNED:
            if row["floor"] is None:
                # A muted track is not measured, so it has no floor to stand on.
                row["code"], row["args"] = "not_measured", {}
            else:
                row["margin_db"] = round(cal["threshold"] - row["floor"], 2)
        rows.append(row)
    margin = combined_margin(rows)
    out = options.as_dict()
    clamped = False
    if margin is not None:
        low, high = RANGES["margin_db"]
        out["margin_db"] = round(min(high, max(low, margin)), 1)
        clamped = not low <= margin <= high
    return {"tracks": rows, "options": out, "learned": margin is not None,
            "clamped": clamped, "learned_margin_db": margin}
