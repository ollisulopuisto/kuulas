"""Which recordings are worth transcribing (owner, 2026-10-20: music is not).

A recording is skipped when EVERY clip that uses it is on a music-kind track. One
on a speech track too is still transcribed (the speech clip needs the words), and one
used nowhere is transcribed as before. Pure: ``Project`` in, answers out. The same rule
is in ``ui/transcribable.js``; the server applies it in ``Session.transcribe`` so no
entry point (menu, panel, Colab upload, API) can bypass it.
"""

from __future__ import annotations

from .model import Project


def music_only_ids(p: Project) -> set[str]:
    """Ids of recordings with at least one clip, all of them on music tracks."""
    on_music: set[str] = set()
    elsewhere: set[str] = set()
    for track in p.tracks:
        target = on_music if track.kind == "music" else elsewhere
        target.update(clip.media for clip in track.clips)
    return on_music - elsewhere


def is_transcribable(p: Project, media_id: str) -> bool:
    return media_id not in music_only_ids(p)
