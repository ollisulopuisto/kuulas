"""Level blocks (Auto-mix in Kuulas, phase 2): the automixer's speech block
levelling, shown and applied as editable clip gains.

The rule is speechmix's (``speechmix.blocks``: ``block_gains``, ``loud_spans``),
fed here the way ``automixer.stems_mix.review`` feeds it:

* a **block** is a speaker's own speech between pauses of 1.5 s or more; its level
  is the median of the energy in 3 s windows, and a block more than 3 dB off the
  speaker's reference level gets the constant gain that brings it back (cuts up
  to 18 dB, boosts up to 6 dB);
* a **loud spot** inside a block (a stretch 4 dB over its block, 1 s or more) is
  emphasis, not a level error: listed, never changed;
* *own* speech is the lane being active and at most 6 dB under the loudest active
  lane (``masks.DUCK_DOMINANCE_DB``), so another speaker's leakage on a mic is not
  mistaken for the owner's level.

**As heard.** The levels include each clip's gain (``analysis.track_levels(...,
heard=True)``), so the command is repeatable: after Apply the same measurement reads
~0 and a second Apply changes nothing. Whether a hop is speech (``on``) is decided
on the raw levels, as Auto-Silence does, so a clip gain never moves that decision.

**Applying** writes the result as clip gain, no media change, no gap: the clips of
each track of the speaker are split (``ops.split_clip``) in the middle of the pause
between two blocks, the same place ``speechmix`` changes the gain, and the gain is
ADDED to the ``gain_db`` the pieces already have (never overwritten). The two
pieces at a new cut get a ``RAMP_S`` fade out / in, so a step in the bleed between
the sentences cannot click; ``speechmix`` ramps 50 ms there, the clip model has
fades but no gain ramp, and a 20 ms dip inside a pause of at least 1.5 s is
inaudible. Soft cuts (``Clip.muted``) are split and get the gain like any piece, so
restoring one brings the level with it. Each track is edited on its own, whatever
the groups: sync is per media and a group only ties selection and movement.

Memory: the levels are one float per 20 ms hop and track (docs/MEMORY.md); the
audio is only streamed when the media has no cached envelope.
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_right
from dataclasses import dataclass, field, replace
from itertools import pairwise
from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
from speechmix import blocks, grid, masks

from . import analysis, caches, ops
from .messages import t
from .ops import CLIP_GAIN_RANGE, EditError

if TYPE_CHECKING:
    from .model import Project, Track

#: Bump when the numbers this module computes change (the ``key``).
ALGORITHM = "block-level@1"

#: Fade out / in on the two pieces at a new cut, seconds.
RAMP_S = 0.02


def speech_tracks(p: Project) -> list[Track]:
    """The tracks it levels: speech, with clips, not muted."""
    return [t for t in p.tracks if t.kind == "speech" and t.clips and not t.mute]


def key(p: Project) -> str:
    """What a measurement depends on, as a content key (``caches.key``): the media
    hashes and the speech tracks as they sound (clips with their gains and soft cuts;
    not the track gain, name, pan or ducking, which it does not read). Raises
    ``caches.CacheKeyError`` when it cannot be made (fail closed)."""
    skip = ("name", "target_lufs", "solo", "pan", "bus", "gain_db", "automation")
    tracks = speech_tracks(p)
    shas = sorted({p.media_item(c.media).sha256 for t in tracks for c in t.clips})
    params = {"rate": p.rate,
              "speech": [{k: v for k, v in t.to_dict().items() if k not in skip}
                         for t in tracks]}
    return caches.key(shas, params, ALGORITHM)


# -- measuring -------------------------------------------------------------------


def _levels(p: Project, store, track: Track):
    raw, valid = analysis.track_levels(p, store, track)
    if not any(c.gain_db for c in track.clips if not c.muted):
        return raw, valid, raw
    heard, _ = analysis.track_levels(p, store, track, heard=True)
    return raw, valid, heard


def _lanes(p: Project, store):
    """One lane per speaker: ``on`` from the raw levels (``grid.lane``, the
    decision), ``level`` from what plays. ``(lane, [track ids])`` in track order."""
    tracks = speech_tracks(p)
    measured = analysis.map_tracks(lambda tr: _levels(p, store, tr), tracks)
    order: list[str] = []
    parts: dict[str, list] = {}
    heard: dict[str, list[np.ndarray]] = {}
    ids: dict[str, list[str]] = {}
    for track, (raw, valid, level) in zip(tracks, measured, strict=True):
        speaker = track.speaker or track.name
        if speaker not in parts:
            order.append(speaker)
            parts[speaker], heard[speaker], ids[speaker] = [], [], []
        floor = grid.noise_floor(grid.smooth(raw), valid)
        parts[speaker].append((raw, valid, floor, grid.FLOOR_MARGIN_DB, 0.0))
        heard[speaker].append(level)
        ids[speaker].append(track.id)
    out = []
    for speaker in order:
        decided = grid.lane(speaker, parts[speaker])
        level = np.maximum.reduce(heard[speaker])
        out.append((SimpleNamespace(name=speaker, on=decided.on, level=level),
                    ids[speaker]))
    return out


def _own_voice(lanes) -> list[np.ndarray]:
    """Per lane: when it is the owner's voice (``stems_mix.own_voice``): active and
    at most ``DUCK_DOMINANCE_DB`` under the loudest active lane."""
    active = np.stack([lane.on for lane in lanes])
    levels = np.stack([lane.level for lane in lanes])
    loudest = np.where(active, levels, -300.0).max(axis=0)
    keep = active & (levels >= loudest - masks.DUCK_DOMINANCE_DB)
    return list(keep)


def _frames(seconds: float, rate: int) -> int:
    return round(seconds * rate)


def measure(p: Project, store) -> dict:
    """``{speakers: [{name, track_ids, blocks, loud}], threshold_db, max_cut_db,
    max_boost_db, key, rate, reason}`` for the snapshot ``p``. ``reason`` is
    ``"no_speech"`` (and no speakers) when there is nothing to level. Positions are
    timeline frames. Pure on the snapshot: the caller holds no lock."""
    out = {"speakers": [], "reason": None, "rate": p.rate, "algorithm": ALGORITHM,
           "threshold_db": blocks.THRESHOLD_DB, "max_cut_db": blocks.MAX_CORRECTION_DB,
           "max_boost_db": blocks.MAX_BOOST_DB}
    try:
        out["key"] = key(p)
    except caches.CacheKeyError:
        out["key"] = None
    if not speech_tracks(p):
        return {**out, "reason": "no_speech"}
    found = _lanes(p, store)
    own = _own_voice([lane for lane, _ in found])
    for (lane, ids), mine in zip(found, own, strict=True):
        found_blocks = blocks.block_gains(lane.level, mine)
        loud = blocks.loud_spans(lane.level, mine, found_blocks)
        out["speakers"].append({
            "name": lane.name, "track_ids": ids,
            "blocks": [{
                "id": f"{lane.name}#{i}", "start": _frames(b.start, p.rate),
                "end": _frames(b.end, p.rate), "own_s": round(b.own_s, 1),
                "level_db": round(b.level_db, 1),
                "deviation_db": round(b.deviation_db, 1), "gain_db": b.gain_db,
            } for i, b in enumerate(found_blocks)],
            "loud": [{"start": _frames(x.start, p.rate), "end": _frames(x.end, p.rate),
                      "excess_db": x.excess_db} for x in loud]})
    return out


def check(measured) -> None:
    """Refuse a measurement that is missing, has nothing to apply or is malformed."""
    if not isinstance(measured, dict):
        raise EditError("error.edit.bad_arguments", name="level_blocks",
                        detail="measured")
    if measured.get("reason") == "no_speech":
        raise EditError("error.block_level.no_speech")
    speakers = measured.get("speakers")
    if (not isinstance(speakers, list) or not isinstance(measured.get("key"), str)
            or not all(isinstance(s, dict) and isinstance(s.get("blocks"), list)
                       and isinstance(s.get("track_ids"), list) for s in speakers)):
        raise EditError("error.edit.bad_arguments", name="level_blocks",
                        detail="measured")


# -- applying --------------------------------------------------------------------


@dataclass
class Report:
    """What an apply did: ``blocks`` changed, ``left_out`` changed blocks the user
    unticked, ``tracks`` edited, ``clamped`` clips that hit the gain range,
    ``markers`` added."""

    blocks: int = 0
    left_out: int = 0
    tracks: int = 0
    clamped: int = 0
    markers: int = 0
    names: list[str] = field(default_factory=list)


def _cut_at(p: Project, track_id: str, frame: int, ramp: int) -> Project:
    """Split every clip of the track that ``frame`` lies inside, and ramp the two
    pieces at the cut."""
    for clip in [c for c in p.track(track_id).clips if c.start < frame < c.end]:
        right_id = ops.new_id("c")
        p = ops.split_clip(p, clip.id, frame, right_id)
        left = next(c for c in p.track(track_id).clips if c.id == clip.id)
        right = next(c for c in p.track(track_id).clips if c.id == right_id)
        p = ops.set_clip(p, left.id, fade_out=min(ramp, left.length))
        p = ops.set_clip(p, right.id, fade_in=min(ramp, right.length))
    return p


def _clamped(value: float) -> float:
    low, high = CLIP_GAIN_RANGE
    return round(max(low, min(high, value)), 2)


def _speaker_gains(speaker: dict, skip: set[str]) -> tuple[list[int], list[float], int]:
    """``(boundaries, gains per segment, changed blocks left out)``: the segments
    are the blocks, each owning the time to the middle of the pause toward its
    neighbours (the first from the start, the last to the end)."""
    rows = sorted(speaker["blocks"], key=lambda b: b["start"])
    bounds = [(a["end"] + b["start"]) // 2 for a, b in pairwise(rows)]
    gains, left_out = [], 0
    for row in rows:
        gain = float(row["gain_db"])
        if row["id"] in skip and gain:
            left_out += 1
            gain = 0.0
        gains.append(gain)
    return bounds, gains, left_out


def apply(p: Project, measured: dict, skip=(),
          markers: bool = False) -> tuple[Project, Report]:
    """``p`` with the measured blocks levelled, and what was done. ``skip``: block
    ids left alone. ``markers``: also a marker at each loud spot."""
    skipped = {str(x) for x in skip}
    report = Report()
    ramp = _frames(RAMP_S, p.rate)
    for speaker in measured["speakers"]:
        bounds, gains, left_out = _speaker_gains(speaker, skipped)
        report.left_out += left_out
        if not any(gains):
            continue
        report.blocks += sum(1 for g in gains if g)
        cuts = [b for i, b in enumerate(bounds) if gains[i] or gains[i + 1]]
        for track_id in speaker["track_ids"]:
            try:
                p.track(track_id)
            except KeyError:
                raise EditError("error.block_level.stale") from None
            for cut in cuts:
                p = _cut_at(p, track_id, cut, ramp)
            for clip in p.track(track_id).clips:
                gain = gains[bisect_right(bounds, clip.start + clip.length // 2)]
                if not gain:
                    continue
                new = _clamped(clip.gain_db + gain)
                report.clamped += int(abs(new - (clip.gain_db + gain)) > 0.005)
                p = ops.set_clip(p, clip.id, gain_db=new)
            report.tracks += 1
        report.names.append(speaker["name"])
    if markers:
        for speaker in measured["speakers"]:
            for spot in speaker.get("loud", []):
                label = t("block_level.loud_marker", speaker=speaker["name"],
                          excess=f"{spot['excess_db']:+.1f}")
                p = ops.add_marker(p, None, label, int(spot["start"]))
                report.markers += 1
    return p, report


# -- the record ------------------------------------------------------------------


def signature(track: Track) -> str:
    """The clips of a track as they sound for the levelling: media, place, cut,
    gain, soft cut. Any change to them makes the record stale."""
    rows = [[c.media, c.start, c.offset, c.length, c.gain_db, c.muted]
            for c in track.clips]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


def record(p: Project, report: Report, at: str | None = None) -> dict:
    """The ``Project.mix_done["block_level"]`` entry for the project AFTER the
    apply (``p``): the export can tell the automixer its block levelling is done
    (``block_level_current``). ``applied`` is a stage, not a number."""
    return {"applied": True, "blocks": report.blocks, "algorithm": ALGORITHM,
            "tracks": {tr.id: signature(tr) for tr in speech_tracks(p)},
            **({"set_at": at} if at else {})}


def block_level_current(p: Project) -> dict | None:
    """The recorded block level, only while it still holds: the same audible speech
    tracks with the clips (cuts, gains, soft cuts) it left. None otherwise."""
    entry = (p.mix_done or {}).get("block_level")
    if not isinstance(entry, dict) or entry.get("applied") is not True:
        return None
    tracks = entry.get("tracks")
    if not isinstance(tracks, dict):
        return None
    now = {tr.id: signature(tr) for tr in speech_tracks(p)}
    return entry if now == tracks else None


def summary(report: Report) -> str:
    return t("ui.block_level.done", blocks=report.blocks, tracks=report.tracks)


def with_record(p: Project, report: Report, at: str | None) -> Project:
    """``p`` with the record, or without any older one, when every changed block was
    applied (a block left out is one the automixer must still level)."""
    done = dict(p.mix_done or {})
    if report.left_out:
        done.pop("block_level", None)
    else:
        done["block_level"] = record(p, report, at)
    return replace(p, mix_done=done)
