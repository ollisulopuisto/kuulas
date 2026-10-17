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
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from nhsx import musicbed
from nhsx.activity import GAP_CLOSE_S, MIN_RUN_S
from speechmix import envelopes, grid, masks
from speechmix.dsp import FLOOR_DB
from speechmix.stems import Lanes

from . import gate, levels, ops
from .media import workers
from .messages import t
from .mixer import Store
from .model import Project, Track

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
MIN_OPEN_S = 0.4
MIN_CLOSED_S = 0.3

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


def speech_lanes(p: Project, store: Store) -> Lanes:
    """One lane per speaker across speech and speech-mix tracks.

    Tracks with the same speaker are grouped into one lane. Tracks are
    measured one per core: each measurement is independent, numpy releases
    the GIL in the heavy parts, and the decision below is per lane, so the
    result is the same as serial.
    """
    tracks = [t for t in p.tracks if t.kind in ("speech", "speech-mix")
              and not t.mute and t.clips]
    if not tracks:
        return Lanes(speakers=[])
    with ThreadPoolExecutor(max_workers=max(1, min(len(tracks), workers()))) as pool:
        measured = list(pool.map(lambda track: track_levels(p, store, track), tracks))

    speaker_order: list[str] = []
    speaker_parts: dict[str, list] = {}
    for track, (db, valid) in zip(tracks, measured, strict=True):
        speaker = track.speaker or track.name
        floor = grid.noise_floor(grid.smooth(db), valid)
        part = (db, valid, floor, grid.FLOOR_MARGIN_DB, 0.0)
        if speaker not in speaker_parts:
            speaker_order.append(speaker)
            speaker_parts[speaker] = []
        speaker_parts[speaker].append(part)

    lanes = [grid.lane(speaker, speaker_parts[speaker]) for speaker in speaker_order]
    return Lanes(speakers=lanes)


def duck_settings(depth_db: float = masks.DUCK_DB) -> SimpleNamespace:
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


def raw_silence_ranges(p: Project, store: Store) -> dict[str, gate.Gate]:
    """Per speech track, the closed ranges exactly as the measurement gives
    them, one per toggle, before ``silence_ranges`` merges them.

    The measurement is made on the raw sources, gate or no gate: the gate
    this replaces must not hide the audio it is being decided from, or a
    second run could never reopen a stretch the first one closed.

    Closed where the owner is not talking (own floor + margin, pauses under
    ``GAP_CLOSE_S`` bridged, blips under ``MIN_RUN_S`` dropped, padded by
    the duck lookahead and hold) or where another mic dominates it
    (``masks.duck_masks``: the louder mic wins, so bleed does not hold a
    mic open).
    """
    lanes = speech_lanes(_ungated(p), store)
    if not lanes.speakers:
        return {}
    hop = hop_frames(p.rate)
    ducked = masks.duck_masks(lanes, duck_settings())
    lane_by_name = {lane.name: lane for lane in lanes.speakers}
    out = {}
    for track in speech_tracks(p):
        speaker = track.speaker or track.name
        lane = lane_by_name.get(speaker)
        if lane is None:
            continue
        talk = masks.close_gaps(np.asarray(lane.on, dtype=bool), GAP_CLOSE_S)
        talk = masks.drop_short(talk, MIN_RUN_S)
        talk = _dilate(talk, masks.hops(OPEN_BEFORE_S), masks.hops(OPEN_AFTER_S))
        closed = ~talk
        if lane.name in ducked:
            closed |= np.asarray(ducked[lane.name], dtype=bool)[: closed.size]
        out[track.id] = gate.ranges_from_mask(closed, hop)
    return out


def silence_ranges(p: Project, store: Store) -> dict[str, gate.Gate]:
    """Per speech track, the merged timeline ranges where its mic should be
    closed (WP44): ``raw_silence_ranges`` with every open stretch under
    ``MIN_OPEN_S`` closed and every closed stretch under ``MIN_CLOSED_S``
    dropped (``gate.merge_ranges``)."""
    min_open = round(MIN_OPEN_S * p.rate)
    min_closed = round(MIN_CLOSED_S * p.rate)
    return {track_id: gate.merge_ranges(ranges, min_open, min_closed)
            for track_id, ranges in raw_silence_ranges(p, store).items()}


def auto_silence(p: Project, store: Store,
                 track_ids: Iterable[str] | None = None) -> Project:
    """Close each speech mic where it should be closed, as a merged gate on
    the track (WP44). Clips are never split. ``track_ids`` limits
    which tracks are changed; every mic is still measured, because whether
    one is closed depends on the others (bleed)."""
    only = None if track_ids is None else set(track_ids)
    for track_id, ranges in silence_ranges(p, store).items():
        if only is None or track_id in only:
            # Replaces the track's gate: a second run does not pile up, and a
            # track that now needs no closing is opened again.
            p = ops.set_gate(p, track_id, ranges)
    return p


def automix(p: Project, store: Store, depth_db: float = masks.DUCK_DB) -> Project:
    """Write speechmix's ducking into each speech track's automation."""
    lanes = speech_lanes(p, store)
    ducks = envelopes.duck_envelopes(lanes, duck_settings(depth_db), 0.0)
    for track in speech_tracks(p):
        speaker = track.speaker or track.name
        points = [(round(t * p.rate), db) for t, db in ducks.get(speaker, [])]
        p = ops.set_track_automation(p, track.id, points)
    return p


def anyone_talking_intervals(p: Project, store: Store) -> list[tuple[float, float]]:
    """Timeline intervals [(start_s, end_s), ...] where anyone is talking.

    Built from speech and speech-mix lanes with pauses under GAP_CLOSE_S
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


def duck_music(p: Project, store: Store) -> Project:
    """Write nhsx.musicbed.curve as track automation on every music track."""
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

