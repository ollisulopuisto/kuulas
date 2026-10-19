"""Measuring for the clipboard preview level (WP82); the arithmetic is in
``preview_level``. Each call takes snapshots and reads only the audio it
needs, 60 s at a time: the caller does not hold the session lock."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import loudness_curve, mixer, preview_level

if TYPE_CHECKING:
    from pathlib import Path

    from .model import Project


def project_reference(project: Project, store: mixer.Store | None,
                      cache_root: str | Path | None) -> tuple[float, float | None]:
    """``(reference LUFS, project peak dBFS or None)`` from the speech tracks'
    cached analysis; the conservative default when there is nothing to hear."""
    if store is None or not any(t.clips for t in project.tracks):
        return preview_level.reference_lufs([], None), None
    levels, peak = loudness_curve.speech_levels(project, store, cache_root)
    return preview_level.reference_lufs(levels, peak), peak


def entry_level(preview: Project,
                store: mixer.Store) -> tuple[float | None, float | None]:
    """``(LUFS, peak dBFS)`` of the entry as the preview would play it, over
    its own clips only (the preview project holds nothing else)."""
    acc = loudness_curve.Accumulator(preview.rate)
    step = loudness_curve.CHUNK_SEC * preview.rate
    for first in range(0, preview.length, step):
        acc.add(mixer.mix(preview, store, first, min(step, preview.length - first)))
    result = acc.result()
    return result.integrated, result.true_peak_db
