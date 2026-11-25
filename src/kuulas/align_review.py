"""An isolated timing proposal. Preview and apply use exactly the same plan."""
from __future__ import annotations

import itertools
import math
import uuid
from dataclasses import replace

from . import ops
from .align_errors import SyncError, fail
from .align_job import snapshot_key


class Review:
    """Server-owned snapshot and offsets, in integer project frames.

    No destructive overwrite: an individual piece cannot cross its neighbours.
    A whole-track move preserves every gap. Media and clip source ranges stay intact.
    """

    def __init__(self, project, track_ids, clip_ids=None):
        wanted = set(track_ids)
        tracks = [t for t in project.tracks if t.id in wanted]
        if (len(wanted) != len(track_ids) or len(tracks) != len(wanted)
                or not 2 <= len(tracks) <= 32
                or any(not t.clips or len(t.clips)>64 for t in tracks)):
            fail("selection")
        # Only some pieces: two separately recorded sets of files on the same tracks are
        # synced one set at a time. The other pieces stay where they are and are never
        # measured. None: every piece of the tracks, as before.
        self.clip_ids = None if clip_ids is None else frozenset(clip_ids)
        if self.clip_ids is not None and any(
                not any(c.id in self.clip_ids for c in t.clips) for t in tracks):
            fail("selection")
        self.id = uuid.uuid4().hex
        self.project = project
        self.key = snapshot_key(project)
        self.track_ids = tuple(t.id for t in tracks)
        self.anchor = tracks[0].id
        self.offsets = {c.id: 0 for t in tracks for c in t.clips}
        self.suggestion = dict(self.offsets)
        self.result = None
        self.revision = 0

    def takes_part(self, clip_id):
        """Is this piece in the review (not left out by the choice of pieces)?"""
        return self.clip_ids is None or clip_id in self.clip_ids

    def check(self, project):
        if snapshot_key(project) != self.key:
            fail("stale")

    def move(self, track_id, frames, clip_id=None):
        if type(frames) is not int or abs(frames) > self.project.rate * 4 * 3600:
            fail("offset")
        if track_id not in self.track_ids or track_id == self.anchor:
            fail("anchor")
        track = self.project.track(track_id)
        ids = [c.id for c in track.clips
               if self.takes_part(c.id) and (clip_id is None or c.id == clip_id)]
        if not ids:
            fail("selection")
        offsets = dict(self.offsets)
        for cid in ids:
            offsets[cid] = frames if clip_id is not None else self.offsets[cid] + frames
        self.preview(offsets)
        self.offsets = offsets
        self.revision += 1

    def preview(self, offsets=None):
        offsets = self.offsets if offsets is None else offsets
        tracks = []
        moved = {t.id for t in self.project.tracks
                 if any(offsets.get(c.id, 0) for c in t.clips)}
        prepared = ops._materialize_legacy_gates(self.project, moved)
        for track in prepared.tracks:
            clips = tuple(replace(c, start=c.start + offsets.get(c.id, 0))
                          for c in track.clips)
            if any(c.start < 0 for c in clips):
                fail("negative")
            # Preserve ordering and existing overlaps. Never create a new collision
            # or enlarge an old overlap while shifting individual pieces.
            old = sorted(track.clips, key=lambda c: (c.start, c.id))
            by_id = {c.id: c for c in clips}
            for a, b in itertools.combinations(old, 2):
                aa, bb = by_id[a.id], by_id[b.id]
                if bb.start < aa.start or max(0, aa.end-bb.start) > max(0, a.end-b.start):
                    fail("collision")
            tracks.append(replace(track, clips=clips))
        return replace(self.project, tracks=tuple(tracks))

    def reset(self):
        self.offsets = dict(self.suggestion)
        self.revision += 1

    def set_result(self, result):
        if result.get("snapshot") != self.key:
            fail("stale")
        self.result = result
        # Suggestions remain proposals, not a client-authoritative apply payload.
        for row in result.get("tracks", []):
            delta = row.get("delta")
            if row.get("status") != "proposal" or type(delta) not in (int, float):
                continue
            if not math.isfinite(delta):
                continue
            track = self.project.track(row["track"])
            proposal = {**self.suggestion,
                        **{c.id: round(delta*self.project.rate) for c in track.clips
                           if self.takes_part(c.id)}}
            try:
                self.preview(proposal)
            except SyncError:
                row["status"] = "blocked"
                continue
            self.suggestion = proposal
        self.offsets = dict(self.suggestion)
        self.revision += 1

    def view(self):
        return {"id": self.id, "anchor": self.anchor, "tracks": self.track_ids,
                "clips": None if self.clip_ids is None else sorted(self.clip_ids),
                "revision": self.revision, "offsets": self.offsets,
                "suggestion": self.suggestion, "result": self.result,
                "project": self.preview().to_dict()}
