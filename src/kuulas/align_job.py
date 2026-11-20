"""Read-only automatic-sync analysis on a frozen project snapshot.

The worker returns proposals, never moves clips or writes variants. A proposal
with excluded windows is not ready to apply until boundary checks explain them.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from . import priority
from .align_proposal import propose
from .align_sound import measure
from .align_stream import read_envelope
from .media import streaming
from .messages import KuulasError
from .model import Project


def snapshot_key(project: Project) -> str:
    """Any project edit invalidates acceptance, not only a selected clip move."""
    return hashlib.sha256(json.dumps(project.to_dict(), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def analyze(project: Project, store, clip_ids: list[str]) -> dict:
    """Analyze selected clips in track order, topmost as reference, without edits.

    At most one clip per track. Fail before reads on a stale/invalid selection.
    Source time, timeline time and frame offsets stay distinct in the result.
    Partial/offline/too-large sources are explicit non-proposals, not silence.
    """
    wanted = set(clip_ids)
    selected = [(track, clip) for track in project.tracks for clip in track.clips
                if clip.id in wanted]
    if (len(clip_ids) != len(wanted) or len(selected) != len(wanted)
            or len(selected) < 2 or len(selected) > 32
            or len({track.id for track, _ in selected}) != len(selected)):
        raise ValueError("invalid automatic-sync clip selection")

    def source(clip):
        priority.checkpoint()
        try:
            if hasattr(store, "partial_info") and store.partial_info(clip.media):
                return None, "partial"
            path = store.transcription_path(clip.media)
            if not path.is_file():
                return None, "offline"
        except (KuulasError, OSError, KeyError):
            return None, "offline"
        media = project.media_item(clip.media)
        if (clip.offset < 0 or clip.length <= 0
                or clip.offset + clip.length > media.frames):
            return None, "invalid_source_range"
        if clip.length > 4 * 3600 * project.rate:
            return None, "over_limit"
        with streaming():
            data = read_envelope(
                lambda first, count: store.read(clip.media, first, count),
                                 rate=project.rate, start=clip.offset, frames=clip.length)
        return data, "measured"

    _, reference = selected[0]
    ref, ref_status = source(reference)
    results = []
    for _, clip in selected[1:]:
        if ref is None:
            results.append({"clip": clip.id, "status": "reference_" + ref_status})
            continue
        candidate, status = source(clip)
        if candidate is None:
            results.append({"clip": clip.id, "status": status})
            continue
        measurements = measure(ref, candidate)
        proposal = propose(measurements)
        results.append({
            "clip": clip.id,
            "status": "proposal" if proposal is not None else "unmatched",
            "measurements": measurements,
            "proposal": asdict(proposal) if proposal is not None else None,
            "timeline_delta": ((reference.start - clip.start) / project.rate
                               + proposal.offset) if proposal is not None else None,
        })
        # Only the reference and this candidate envelope are retained.
    return {"snapshot": snapshot_key(project), "reference": reference.id,
            "candidates": results}
