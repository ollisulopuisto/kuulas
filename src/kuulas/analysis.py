"""Who is talking, and what to do about the microphones that are not.

The decision is speechmix's (``grid.lane``, ``masks.duck_masks``,
``envelopes.duck_envelopes``); this module only feeds it levels from the
project's own timeline. Two consumers:

* ``auto_silence``: Pro Cut style. Each speech mic is closed wherever its
  owner is not talking, as one merged gate per track (``Track.gate``).
* ``automix``: the automixer's ducking, written as track automation points
  you can drag, not baked into samples.

Only ``kind == "speech"`` tracks are measured. They are read as mono (a
stereo source is averaged, as ``speechmix.rms`` does), so stereo music
cannot register as a talker.

Playback first (docs/PLAYBACK-PRIORITY.md): the editor runs these through
``offload``, in a separate low-priority process with its own GIL. When they do
run here (a store the worker cannot reopen, a worker that failed, tests), the
per-track pool is ``priority.gated_map`` and every audio chunk passes
``priority.checkpoint``: background callers pause while audio plays.
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Iterable
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from nhsx import musicbed
from nhsx.activity import GAP_CLOSE_S, MIN_RUN_S
from speechmix import envelopes, grid, masks
from speechmix.dsp import FLOOR_DB
from speechmix.stems import Lanes

from . import bleed_relative, gate, levels, ops, priority
from .media import workers
from .messages import t
from .mixer import Store
from .model import Project, Track
from .silence_options import (
    DEFAULT_MIN_CLOSED_S,
    DEFAULT_MIN_OPEN_S,
    SilenceOptionError,
    SilenceOptions,
)

#: Speech tail and onset kept open around the detected talk, in seconds.
#: speechmix's own ducking values (lookahead before, hold after), so a
#: mic opens and closes where the automixer would.
OPEN_BEFORE_S = masks.DUCK_LOOKAHEAD
OPEN_AFTER_S = masks.DUCK_HOLD

#: The merge of the measured toggles into a gate (WP44, ``gate.merge_ranges``):
#: an open stretch shorter than MIN_OPEN_S is closed, a closed stretch shorter
#: than MIN_CLOSED_S is dropped. Tuned on the synthetic four-voice
#: conversations of ``tests/gate_fixtures.py`` (6 seeds, bleed 0.2 to 0.8,
#: turns of 0.2 to 3.5 s, 300 s, 4 mics; 129 to 198 raw toggles each when the
#: room is busy): speechmix's own smoothing leaves no open stretch under
#: 0.8 s, and the shortest closed ones are 0.14 to 0.6 s. At 0.4 s / 0.3 s
#: the merge bridges nothing and drops at most one stretch (closed time moves
#: by under 0.1 %); at 0.8 s / 0.5 s it still moves under 0.2 %; at 1.5 s /
#: 0.8 s it merges 15 to 30 % of the ranges and moves the closed time by 2 to
#: 12 %, which is audible as words cut off. So the owner's starting values
#: stay: a floor for noisier real recordings, not a reshaping of the clean
#: ones. MIN_OPEN_S is above a breath between two words, so a mic never
#: flutters open for it; MIN_CLOSED_S is ten times the 30 ms edge ramp, so a
#: closed range is never mostly ramp.
MIN_OPEN_S = DEFAULT_MIN_OPEN_S
MIN_CLOSED_S = DEFAULT_MIN_CLOSED_S

CHUNK_SEC = 60

log = logging.getLogger("kuulas.analysis")


def speech_tracks(p: Project) -> list[Track]:
    return [t for t in p.tracks if t.kind == "speech" and t.clips]


def hop_frames(rate: int) -> int:
    return round(rate * grid.HOP_SEC)


def track_levels(p: Project, store: Store, track: Track) -> tuple[np.ndarray, np.ndarray]:
    """``(dB per hop, valid)`` over the timeline, from the raw sources.

    Raw: no clip or track gain, because the decision's margin is over the
    track's own floor and gain must not move it (``grid.lane``). The track's
    gate is not a gain but a mute, and is left out like a muted clip.

    Composed from the store's cached per-media envelopes when it has them
    (``MediaStore.envelope``), so an edit reads no audio (WP36); measured
    from the audio otherwise, which gives the same numbers.
    """
    clips = [c for c in track.clips if not c.muted]
    composed = _from_envelopes(p, store, clips, track.id)
    if composed is None:
        composed = _from_audio(p, store, clips)
    mean_sq, valid = composed
    if track.gate:
        # A gated hop is inaudible, as one under a muted clip is: no level,
        # not valid. Only hops wholly inside the gate; a hop the gate merely
        # touches is still partly heard.
        shut = gate.full_hops(track.gate, mean_sq.size, hop_frames(p.rate))
        mean_sq = np.where(shut, 0.0, mean_sq)
        valid = valid & ~shut
    db = 10.0 * np.log10(np.maximum(mean_sq, 1e-12))
    return np.maximum(db, FLOOR_DB).astype(np.float32), valid


def _hops(p: Project) -> int:
    return int(np.ceil(p.length / hop_frames(p.rate))) if p.length else 0


def _from_envelopes(p: Project, store: Store, clips,
                    track_id: str) -> tuple[np.ndarray, np.ndarray] | None:
    """Mean square per hop from envelopes, or None when they cannot give the
    audio path's answer: no envelope provider, a media without one, or clips
    that overlap (their waveforms add before they are squared)."""
    provider = getattr(store, "envelope", None)
    if provider is None:
        return None
    hop = hop_frames(p.rate)
    block = levels.block_frames(hop)
    n = _hops(p)
    end = n * hop
    spans = sorted((c for c in clips if min(c.end, end) > max(c.start, 0)),
                   key=lambda c: c.start)
    if any(b.start < a.end for a, b in itertools.pairwise(spans)):
        log.info(t("log.analysis.overlap", track_id=track_id))
        return None
    energy = np.zeros(n, dtype=np.float64)
    valid = np.zeros(n, dtype=bool)
    for c in spans:
        try:
            frames = p.media_item(c.media).frames
        except KeyError:
            return None
        blocks = provider(c.media, block)
        if blocks is None:
            return None
        lo, hi = max(c.start, 0), min(c.end, end)
        edges = np.concatenate(([lo], np.arange((lo // hop + 1) * hop, hi, hop), [hi]))
        upto = levels.energy_upto(blocks, block, frames, edges + (c.offset - c.start))
        np.add.at(energy, edges[:-1] // hop, np.diff(upto))
        valid[lo // hop:(hi - 1) // hop + 1] = True
    return energy / hop, valid


def _from_audio(p: Project, store: Store, clips) -> tuple[np.ndarray, np.ndarray]:
    hop = hop_frames(p.rate)
    n = _hops(p)
    mean_sq = np.zeros(n, dtype=np.float64)
    valid = np.zeros(n, dtype=bool)
    step = (CHUNK_SEC * p.rate // hop) * hop
    for first in range(0, n * hop, step):
        priority.checkpoint()
        count = min(step, n * hop - first)
        buf = np.zeros(count, dtype=np.float64)
        cover = np.zeros(count, dtype=bool)
        for c in clips:
            lo, hi = max(first, c.start), min(first + count, c.end)
            if hi <= lo:
                continue
            audio = store.read(c.media, c.offset + lo - c.start, hi - lo)
            buf[lo - first:hi - first] += audio.mean(axis=0)
            cover[lo - first:hi - first] = True
        h0 = first // hop
        h = count // hop
        mean_sq[h0:h0 + h] = np.mean(np.square(buf[: h * hop]).reshape(h, hop), axis=1)
        valid[h0:h0 + h] = cover[: h * hop].reshape(h, hop).any(axis=1)
    return mean_sq, valid


def speech_lanes(p: Project, store: Store,
                 margin_db: float = grid.FLOOR_MARGIN_DB) -> Lanes:
    """One lane per speaker across speech tracks.

    Tracks with the same speaker are grouped into one lane. Tracks are
    measured one per core: each measurement is independent, numpy releases
    the GIL in the heavy parts, and the decision below is per lane, so the
    result is the same as serial. Under the playback gate: one track at a
    time while the user is busy, none started while audio plays.
    """
    tracks = [t for t in p.tracks if t.kind == "speech"
              and not t.mute and t.clips]
    if not tracks:
        return Lanes(speakers=[])
    measured = priority.gated_map(lambda track: track_levels(p, store, track), tracks,
                                  max(1, min(len(tracks), workers())))

    speaker_order: list[str] = []
    speaker_parts: dict[str, list] = {}
    for track, (db, valid) in zip(tracks, measured, strict=True):
        speaker = track.speaker or track.name
        floor = grid.noise_floor(grid.smooth(db), valid)
        part = (db, valid, floor, margin_db, 0.0)
        if speaker not in speaker_parts:
            speaker_order.append(speaker)
            speaker_parts[speaker] = []
        speaker_parts[speaker].append(part)

    lanes = [grid.lane(speaker, speaker_parts[speaker]) for speaker in speaker_order]
    return Lanes(speakers=lanes)


def duck_settings(depth_db: float = masks.DUCK_DB,
                  dominance_db: float = masks.DUCK_DOMINANCE_DB) -> SimpleNamespace:
    """The settings object the masks read, at speechmix's defaults.

    Same construction as automixer's ``stems_mix``: every ``DUCK_*``
    constant, under both its bare and its ``duck_`` name.
    """
    s = SimpleNamespace(duck=True)
    for name in ("db", "fade", "release", "hold", "lookahead", "min_open",
                 "min_closed", "dominance_db", "min_gap"):
        value = getattr(masks, f"DUCK_{name.upper()}")
        setattr(s, name, value)
        setattr(s, f"duck_{name}", value)
    s.db = s.duck_db = float(depth_db)
    s.dominance_db = s.duck_dominance_db = float(dominance_db)
    return s


def _dilate(mask: np.ndarray, before: int, after: int) -> np.ndarray:
    out = mask.copy()
    idx = np.flatnonzero(mask)
    for k in range(1, before + 1):
        out[np.maximum(idx - k, 0)] = True
    for k in range(1, after + 1):
        out[np.minimum(idx + k, mask.size - 1)] = True
    return out


def _ungated(p: Project) -> Project:
    """``p`` with every gate emptied: what the measurement must see."""
    if not any(t.gate for t in p.tracks):
        return p
    return replace(p, tracks=tuple(replace(t, gate=()) for t in p.tracks))


def raw_silence_ranges(p: Project, store: Store,
                       options: SilenceOptions | None = None) -> dict[str, gate.Gate]:
    """Per speech track, the closed ranges exactly as the measurement gives
    them, one per toggle, before ``silence_ranges`` merges them.

    The measurement is made on the raw sources, gate or no gate: the gate
    this replaces must not hide the audio it is being decided from, or a
    second run could never reopen a stretch the first one closed.

    Closed where the owner is not talking (own floor + ``margin_db``, pauses
    under ``GAP_CLOSE_S`` bridged, blips under ``MIN_RUN_S`` dropped, padded
    by ``open_before_s`` and ``open_after_s``) or where another mic dominates
    it (``masks.duck_masks``: the louder mic wins, so bleed does not hold a
    mic open; a mic within ``dominance_db`` of the loudest stays open). With
    ``method == "compensated"`` the talk is decided by ``bleed_relative``
    instead, calibrated on the hand mutes, and there is no ducking mask.
    """
    opts = options or SilenceOptions()
    if opts.method == "compensated":
        return _compensated_ranges(p, store, opts)
    lanes = speech_lanes(_ungated(p), store, opts.margin_db)
    if not lanes.speakers:
        return {}
    hop = hop_frames(p.rate)
    ducked = masks.duck_masks(lanes, duck_settings(dominance_db=opts.dominance_db))
    lane_by_name = {lane.name: lane for lane in lanes.speakers}
    out = {}
    for track in speech_tracks(p):
        speaker = track.speaker or track.name
        lane = lane_by_name.get(speaker)
        if lane is None:
            continue
        closed = _closed_from_talk(np.asarray(lane.on, dtype=bool), opts)
        if lane.name in ducked:
            closed |= np.asarray(ducked[lane.name], dtype=bool)[: closed.size]
        out[track.id] = gate.ranges_from_mask(closed, hop)
    return out


def _closed_from_talk(on: np.ndarray, opts: SilenceOptions) -> np.ndarray:
    talk = masks.close_gaps(on, GAP_CLOSE_S)
    talk = masks.drop_short(talk, MIN_RUN_S)
    talk = _dilate(talk, masks.hops(opts.open_before_s), masks.hops(opts.open_after_s))
    return ~talk


def hand_mutes(track: Track) -> gate.Gate:
    """The runs of muted clips on ``track``: what the owner muted by hand."""
    return gate.normalise((c.start, c.end) for c in track.clips if c.muted)


def calibration_end(p: Project) -> int:
    """The last frame any speech track's hand mute reaches: the end of the
    stretch the compensated method learns from (0 when there are none)."""
    return max((r[-1][1] for t in speech_tracks(p) if (r := hand_mutes(t))), default=0)


def _unmuted(p: Project) -> Project:
    return replace(p, tracks=tuple(
        replace(t, gate=(), clips=tuple(replace(c, muted=False) for c in t.clips))
        for t in p.tracks))


def _compensated_ranges(p: Project, store: Store,
                        opts: SilenceOptions) -> dict[str, gate.Gate]:
    """The ``bleed_relative`` decision (see there). Calibrated on the hand
    mutes from the start to the last one; without any it cannot run."""
    end = calibration_end(p)
    if end <= 0:
        raise SilenceOptionError("error.silence.no_hand_mutes")
    tracks = [tr for tr in speech_tracks(p) if not tr.mute]
    if len(tracks) < 2:
        return {}
    hop = hop_frames(p.rate)
    q = _unmuted(p)
    measured = priority.gated_map(lambda tr: track_levels(q, store, tr), tracks,
                                  max(1, min(len(tracks), workers())))
    db = np.stack([m[0] for m in measured]).astype(np.float64)
    valid = np.stack([m[1] for m in measured])
    muted = np.zeros(db.shape, dtype=bool)
    for i, tr in enumerate(tracks):
        for a, b in hand_mutes(tr):
            muted[i, -(-a // hop):b // hop] = True
    window = np.arange(db.shape[1]) < -(-end // hop)
    offsets = bleed_relative.estimate_offsets(db, valid, muted, window)
    on = bleed_relative.speaking(db, valid, offsets, presence_db=opts.margin_db)
    return {tr.id: gate.ranges_from_mask(_closed_from_talk(on[i], opts), hop)
            for i, tr in enumerate(tracks)}


def silence_ranges(p: Project, store: Store,
                   options: SilenceOptions | None = None) -> dict[str, gate.Gate]:
    """Per speech track, the merged timeline ranges where its mic should be
    closed (WP44): ``raw_silence_ranges`` with every open stretch under
    ``min_open_s`` closed and every closed stretch under ``min_closed_s``
    dropped (``gate.merge_ranges``)."""
    opts = options or SilenceOptions()
    min_open = round(opts.min_open_s * p.rate)
    min_closed = round(opts.min_closed_s * p.rate)
    return {track_id: gate.merge_ranges(ranges, min_open, min_closed)
            for track_id, ranges in raw_silence_ranges(p, store, opts).items()}


def preview_silence(p: Project, store: Store, options: SilenceOptions | None = None,
                    track_ids: Iterable[str] | None = None) -> list[dict]:
    """What Auto-Silence with ``options`` WOULD close, committing nothing: per
    speech track ``{track_id, name, close_s, stretches, now_s}`` (``now_s``:
    what the track's gate closes today). Pure on the snapshot ``p``, so the
    caller can run it without any lock."""
    only = None if track_ids is None else set(track_ids)
    ranges = silence_ranges(p, store, options)
    rows = []
    for track in speech_tracks(p):
        if track.id not in ranges or (only is not None and track.id not in only):
            continue
        closed = ranges[track.id]
        rows.append({
            "track_id": track.id, "name": track.name,
            "close_s": sum(b - a for a, b in closed) / p.rate,
            "stretches": len(closed),
            "now_s": sum(b - a for a, b in track.gate) / p.rate})
    return rows


def auto_silence(p: Project, store: Store,
                 track_ids: Iterable[str] | None = None,
                 options: SilenceOptions | None = None) -> Project:
    """Close each speech mic where it should be closed, as a merged gate on
    the track (WP44). Clips are never split. ``track_ids`` limits
    which tracks are changed; every mic is still measured, because whether
    one is closed depends on the others (bleed)."""
    return apply_silence(p, silence_ranges(p, store, options), track_ids)


def apply_silence(p: Project, ranges_by_track: dict[str, gate.Gate],
                  track_ids: Iterable[str] | None = None) -> Project:
    """``auto_silence`` with the ranges already measured (``silence_ranges``,
    perhaps by the analysis worker): set them as the tracks' gates."""
    only = None if track_ids is None else set(track_ids)
    for track_id, ranges in ranges_by_track.items():
        if only is None or track_id in only:
            # Replaces the track's gate: a second run does not pile up, and a
            # track that now needs no closing is opened again.
            p = ops.set_gate(p, track_id, ranges)
    return p


def automix(p: Project, store: Store, depth_db: float = masks.DUCK_DB,
            lanes: Lanes | None = None) -> Project:
    """Write speechmix's ducking into each speech track's automation.
    ``lanes``: ``speech_lanes(p, store)`` already measured (the worker's)."""
    lanes = speech_lanes(p, store) if lanes is None else lanes
    ducks = envelopes.duck_envelopes(lanes, duck_settings(depth_db), 0.0)
    for track in speech_tracks(p):
        speaker = track.speaker or track.name
        points = [(round(t * p.rate), db) for t, db in ducks.get(speaker, [])]
        p = ops.set_track_automation(p, track.id, points)
    return p


def anyone_talking_intervals(p: Project, store: Store) -> list[tuple[float, float]]:
    """Timeline intervals [(start_s, end_s), ...] where anyone is talking.

    Built from speech lanes with pauses under GAP_CLOSE_S
    bridged and blips under MIN_RUN_S dropped.
    """
    lanes = speech_lanes(p, store)
    if not lanes.speakers:
        return []
    n = max((len(lane.on) for lane in lanes.speakers), default=0)
    if n == 0:
        return []
    anyone = np.zeros(n, dtype=bool)
    for lane in lanes.speakers:
        on = np.asarray(lane.on, dtype=bool)
        anyone[: on.size] |= on
    bridged = masks.close_gaps(anyone, GAP_CLOSE_S)
    filtered = masks.drop_short(bridged, MIN_RUN_S)
    return [
        (a * grid.HOP_SEC, b * grid.HOP_SEC)
        for a, b, v in masks.runs(filtered.astype(np.int8))
        if v
    ]


def duck_music(p: Project, store: Store,
               intervals: list[tuple[float, float]] | None = None) -> Project:
    """Write nhsx.musicbed.curve as track automation on every music track.
    ``intervals``: ``anyone_talking_intervals`` already measured (the worker's)."""
    if intervals is None:
        intervals = anyone_talking_intervals(p, store)
    first_speech_s = intervals[0][0] if intervals else float("inf")
    music_tracks = [t for t in p.tracks if t.kind == "music"]
    for track in music_tracks:
        points: list[tuple[int, float]] = []
        audible_clips = [c for c in track.clips if not c.muted]
        for clip in sorted(audible_clips, key=lambda c: c.start):
            start_s = clip.start / p.rate
            end_s = clip.end / p.rate
            cold_open = start_s < first_speech_s
            bed_curve = musicbed.curve(start_s, end_s, intervals, cold_open=cold_open)
            if bed_curve is not None:
                for s_offset, db in bed_curve:
                    frame = round((start_s + s_offset) * p.rate)
                    points.append((frame, db))
        points.sort(key=lambda pt: pt[0])
        p = ops.set_track_automation(p, track.id, points)
    return p

