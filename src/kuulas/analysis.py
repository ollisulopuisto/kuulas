"""Who is talking, and what to do about the microphones that are not.

The decision is speechmix's (``grid.lane``, ``masks.duck_masks``,
``envelopes.duck_envelopes``); this module only feeds it levels from the
project's own timeline. Two consumers:

* ``auto_silence``: Pro Cut style. Each speech mic is muted wherever its
  owner is not talking, as muted clip pieces you can see and undo.
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
from types import SimpleNamespace

import numpy as np
from nhsx.activity import GAP_CLOSE_S, MIN_RUN_S
from speechmix import envelopes, grid, masks
from speechmix.dsp import FLOOR_DB
from speechmix.stems import Lanes

from . import levels, ops
from .media import workers
from .messages import t
from .mixer import Store
from .model import Project, Track

#: Speech tail and onset kept open around the detected talk, in seconds.
#: speechmix's own ducking values (lookahead before, hold after), so a
#: mic opens and closes where the automixer would.
OPEN_BEFORE_S = masks.DUCK_LOOKAHEAD
OPEN_AFTER_S = masks.DUCK_HOLD

CHUNK_SEC = 60

log = logging.getLogger("kuulas.analysis")


def speech_tracks(p: Project) -> list[Track]:
    return [t for t in p.tracks if t.kind == "speech" and t.clips]


def hop_frames(rate: int) -> int:
    return round(rate * grid.HOP_SEC)


def track_levels(p: Project, store: Store, track: Track) -> tuple[np.ndarray, np.ndarray]:
    """``(dB per hop, valid)`` over the timeline, from the raw sources.

    Raw: no clip or track gain, because the decision's margin is over the
    track's own floor and gain must not move it (``grid.lane``).

    Composed from the store's cached per-media envelopes when it has them
    (``MediaStore.envelope``), so an edit reads no audio (WP36); measured
    from the audio otherwise, which gives the same numbers.
    """
    clips = [c for c in track.clips if not c.muted]
    composed = _from_envelopes(p, store, clips, track.id)
    if composed is None:
        composed = _from_audio(p, store, clips)
    mean_sq, valid = composed
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
    """One lane per speech track. Tracks are measured one per core: each
    measurement is independent, numpy releases the GIL in the heavy parts,
    and the decision below is per lane, so the result is the same as serial."""
    tracks = speech_tracks(p)
    with ThreadPoolExecutor(max_workers=max(1, min(len(tracks), workers()))) as pool:
        measured = list(pool.map(lambda track: track_levels(p, store, track), tracks))
    lanes = []
    for track, (db, valid) in zip(tracks, measured, strict=True):
        floor = grid.noise_floor(grid.smooth(db), valid)
        lanes.append(grid.lane(track.id, [(db, valid, floor, grid.FLOOR_MARGIN_DB, 0.0)]))
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


def _ranges(mask: np.ndarray, hop: int) -> list[tuple[int, int]]:
    return [(a * hop, b * hop) for a, b, v in masks.runs(mask.astype(np.int8)) if v]


def silence_ranges(p: Project, store: Store) -> dict[str, list[tuple[int, int]]]:
    """Per speech track, timeline ranges where its mic should be muted.

    Closed where the owner is not talking (own floor + margin, pauses under
    ``GAP_CLOSE_S`` bridged, blips under ``MIN_RUN_S`` dropped, padded by
    the duck lookahead and hold) or where another mic dominates it
    (``masks.duck_masks``: the louder mic wins, so bleed does not hold a
    mic open).
    """
    lanes = speech_lanes(p, store)
    if not lanes.speakers:
        return {}
    hop = hop_frames(p.rate)
    ducked = masks.duck_masks(lanes, duck_settings())
    out = {}
    for lane in lanes.speakers:
        talk = masks.close_gaps(np.asarray(lane.on, dtype=bool), GAP_CLOSE_S)
        talk = masks.drop_short(talk, MIN_RUN_S)
        talk = _dilate(talk, masks.hops(OPEN_BEFORE_S), masks.hops(OPEN_AFTER_S))
        closed = ~talk
        if lane.name in ducked:
            closed |= np.asarray(ducked[lane.name], dtype=bool)[: closed.size]
        out[lane.name] = _ranges(closed, hop)
    return out


def auto_silence(p: Project, store: Store,
                 track_ids: Iterable[str] | None = None) -> Project:
    """Mute each speech mic where it should be closed. ``track_ids`` limits
    which tracks are changed; every mic is still measured, because whether
    one is closed depends on the others (bleed)."""
    only = None if track_ids is None else set(track_ids)
    for track_id, ranges in silence_ranges(p, store).items():
        if ranges and (only is None or track_id in only):
            p = ops.mute_ranges(p, track_id, ranges)
    return p


def automix(p: Project, store: Store, depth_db: float = masks.DUCK_DB) -> Project:
    """Write speechmix's ducking into each speech track's automation."""
    lanes = speech_lanes(p, store)
    ducks = envelopes.duck_envelopes(lanes, duck_settings(depth_db), 0.0)
    for track in speech_tracks(p):
        points = [(round(t * p.rate), db) for t, db in ducks.get(track.id, [])]
        p = ops.set_track_automation(p, track.id, points)
    return p
