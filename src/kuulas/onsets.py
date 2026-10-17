"""Transient onset detection and caching (WP19i).

Detects transient onsets per media, caches them by content hash in
``caches/onsets/`` in flicks from the media's start, and maps them to timeline
frames through unmuted clips.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np
from speechmix import dsp, grid

from . import caches, clock
from .messages import t

if TYPE_CHECKING:
    from .media import MediaStore
    from .model import Project

log = logging.getLogger("kuulas.onsets")

#: Algorithm version string; bump whenever the detection logic changes.
ALGORITHM = "onsets@1"
#: Bin duration in milliseconds for the envelope.
BIN_MS = 1
#: Preceding window in milliseconds for baseline comparison.
PRE_MS = 20
#: Threshold in dB above preceding mean level to qualify as an onset.
THRESHOLD_DB = 12.0
#: Minimum separation in milliseconds between adjacent onsets (strongest kept).
MIN_INTERVAL_MS = 50


def cache_params(rate: int) -> dict[str, Any]:
    """Parameters included in the cache key proving what was computed."""
    return {
        "bin_ms": BIN_MS,
        "threshold_db": THRESHOLD_DB,
        "pre_ms": PRE_MS,
        "min_interval_ms": MIN_INTERVAL_MS,
        "floor_margin_db": grid.FLOOR_MARGIN_DB,
        "rate": rate,
    }


def cache_key(media_sha256: str, rate: int) -> str:
    """Content-addressed cache key for onset detection results."""
    return caches.key([media_sha256], cache_params(rate), ALGORITHM)


def detect(audio: np.ndarray, rate: int) -> np.ndarray:
    """Detect transient onsets in ``audio`` at ``rate``.

    Returns a 1D ``int64`` array of onset positions in flicks from the start.
    """
    if audio.ndim == 2:
        mono = audio.mean(axis=0) if audio.shape[0] > 1 else audio[0]
    else:
        mono = audio

    step = max(1, int(rate * BIN_MS / 1000))
    n_bins = mono.size // step
    bins_20 = max(1, PRE_MS // BIN_MS)
    if n_bins < bins_20:
        return np.empty(0, dtype=np.int64)

    peaks = np.abs(mono[: n_bins * step]).reshape(n_bins, step).max(axis=1)

    n_20 = n_bins // bins_20
    env_20 = peaks[: n_20 * bins_20].reshape(n_20, bins_20).max(axis=1)
    env_20_db = dsp.lin_to_db(env_20)
    floor_margin_db = grid.FLOOR_MARGIN_DB
    measured_floor = grid.noise_floor(env_20_db)
    # Ensure synthetic pure tones with no silence have a valid contrast margin
    floor_db = min(measured_floor, float(env_20_db.max() - floor_margin_db - 1.0))

    cumsum = np.pad(np.cumsum(peaks, dtype=np.float64), (1, 0))
    idx = np.arange(n_bins)
    pre_idx = np.maximum(0, idx - bins_20)
    pre_count = np.maximum(1, idx - pre_idx)
    pre_mean = (cumsum[idx] - cumsum[pre_idx]) / pre_count
    pre_mean[0] = 0.0

    level_db = dsp.lin_to_db(peaks)
    pre_mean_db = dsp.lin_to_db(pre_mean)
    diff_db = level_db - pre_mean_db

    candidates = (diff_db >= THRESHOLD_DB) & (level_db >= floor_db + floor_margin_db)
    cand_indices = np.flatnonzero(candidates)
    if cand_indices.size == 0:
        return np.empty(0, dtype=np.int64)

    min_interval_bins = max(1, MIN_INTERVAL_MS // BIN_MS)
    suppressed = np.zeros(n_bins, dtype=bool)
    order = cand_indices[np.argsort(-peaks[cand_indices])]
    selected = []
    for c in order:
        if not suppressed[c]:
            selected.append(c)
            lo = max(0, c - min_interval_bins + 1)
            hi = min(n_bins, c + min_interval_bins)
            suppressed[lo:hi] = True
    selected.sort()

    found_flicks = []
    for b in selected:
        p = peaks[b]
        bin_audio = np.abs(mono[b * step : (b + 1) * step])
        j = int(np.argmax(bin_audio >= 0.5 * p))
        sample_idx = b * step + j
        found_flicks.append(clock.frames_to_flicks(sample_idx, rate))

    return np.array(found_flicks, dtype=np.int64)


def timeline_onsets(
    p: Project,
    onsets_by_media: dict[str, np.ndarray | list[int]],
    track_id: str | None = None,
) -> list[int]:
    """Map media onsets to timeline frames through clips, skipping muted parts."""
    out: list[int] = []
    for track in p.tracks:
        if track_id is not None and track.id != track_id:
            continue
        if track.mute:
            continue
        for clip in track.clips:
            if clip.muted:
                continue
            media_onsets = onsets_by_media.get(clip.media)
            if media_onsets is None or len(media_onsets) == 0:
                continue
            lo, hi = clip.offset, clip.offset + clip.length
            shift = clip.start - clip.offset
            for flick in media_onsets:
                frame_in_media = clock.flicks_to_frames(int(flick), p.rate)
                if lo <= frame_in_media < hi:
                    out.append(frame_in_media + shift)
    return sorted(set(out))


def onsets_for_media(store: MediaStore, media_id: str) -> np.ndarray | None:
    """Read or compute onsets for ``media_id``, cached in ``caches/onsets/``."""
    try:
        meta = store.meta(media_id)
    except (KeyError, ValueError):
        return None
    if store._unreadable(media_id):
        return None

    try:
        key = cache_key(meta["sha256"], store.rate)
    except caches.CacheKeyError:
        log.warning(t("log.cache.no_key", kind="onsets", media_id=media_id))
        return None

    def compute() -> np.ndarray:
        log.info(t("log.cache.recompute", kind="onsets", media_id=media_id))
        audio = store.read(media_id, 0, meta["source_frames"])
        return detect(audio, store.rate)

    spill = caches.path(store.cache_root, "onsets", key, "npy")
    return store.budget.fetch("onsets", key, compute, spill=spill)
