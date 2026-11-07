"""Pasting clips from another project keeps only the used source audio (WP20)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import soundfile as sf

from kuulas import session as session_module
from kuulas.clock import FLICKS
from kuulas.session import Session
from kuulas.source_map import coverage
from kuulas.usage import extract

RATE = 48_000


def _wav(path, seconds: float, seed: int) -> None:
    rng = np.random.default_rng(seed)
    sf.write(
        path,
        (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32),
        RATE,
        subtype="PCM_16",
    )


def test_pasting_a_clip_copies_only_its_range_plus_handles(tmp_path):
    source = Session(tmp_path / "Source.kuulas")
    target = Session(tmp_path / "Target.kuulas")
    try:
        source_path = tmp_path / "long.wav"
        _wav(source_path, 60, 1)
        source.import_media([str(source_path)], copy=True)
        source_media = source.state.media[0]
        source_track = source.state.tracks[0]
        copied = source.clipboard_copy(
            start=25 * RATE,
            end=round(26.5 * RATE),
            track_ids=[source_track.id],
        )["entry"]

        target_path = tmp_path / "target.wav"
        _wav(target_path, 2, 2)
        target.import_media([str(target_path)])
        target_track = target.state.tracks[0]

        source_size = source_path.stat().st_size
        source_path.unlink()
        adopted = target.clipboard_adopt(copied)
        result = target.clipboard_paste(
            adopted["id"],
            at=0,
            mode="overwrite",
            target_tracks={0: target_track.id},
        )

        assert result["placed"] == 1
        assert result["missing"] == []
        pasted = next(
            clip for clip in target.state.track(target_track.id).clips if clip.start == 0
        )
        excerpt = target.state.media_item(pasted.media)
        assert excerpt.sha256 != source_media.sha256
        assert excerpt.excerpt_of == source_media.sha256
        assert excerpt.excerpt_start_flicks == 23 * FLICKS
        assert pasted.offset == 2 * RATE
        uses = extract(target.state)
        assert uses[0].media_sha256 == source_media.sha256
        assert uses[0].from_flicks == 25 * FLICKS
        assert coverage(target.state, source_media.sha256)[0] == [
            (25 * FLICKS, round(26.5 * FLICKS))
        ]
        stored = target.store.working_file(excerpt.id)
        assert stored.stat().st_size < source_size * 0.1
    finally:
        source.close()
        target.close()


def test_paste_does_not_read_a_clipboard_source_outside_project_folder(
    tmp_path, monkeypatch
):
    source = Session(tmp_path / "Source.kuulas")
    target = Session(tmp_path / "Target.kuulas")
    try:
        source_path = tmp_path / "source.wav"
        _wav(source_path, 5, 3)
        source.import_media([str(source_path)], copy=True)
        source_track = source.state.tracks[0]
        copied = source.clipboard_copy(
            start=0, end=RATE, track_ids=[source_track.id]
        )["entry"]
        adopted = target.clipboard_adopt(copied)
        outside = replace(
            target._entry(adopted["id"]), source_project=str(tmp_path)
        )
        calls = []
        monkeypatch.setattr(
            session_module.clipboard_link,
            "candidate_paths",
            lambda *args: calls.append(args) or [],
        )

        assert target._link_missing_media(outside) == outside
        assert calls == []
    finally:
        source.close()
        target.close()


def test_missing_source_working_audio_keeps_clip_missing(tmp_path):
    source = Session(tmp_path / "Source.kuulas")
    target = Session(tmp_path / "Target.kuulas")
    try:
        source_path = tmp_path / "source.wav"
        _wav(source_path, 5, 4)
        source.import_media([str(source_path)], copy=True)
        source_media = source.state.media[0]
        source_track = source.state.tracks[0]
        copied = source.clipboard_copy(
            start=0, end=RATE, track_ids=[source_track.id]
        )["entry"]
        target_path = tmp_path / "target.wav"
        _wav(target_path, 2, 5)
        target.import_media([str(target_path)])
        target_track = target.state.tracks[0]
        existing_clips = target_track.clips
        adopted = target.clipboard_adopt(copied)
        source_path.unlink()
        source.store.working_file(source_media.id).unlink()

        result = target.clipboard_paste(
            adopted["id"], at=0, mode="overwrite",
            target_tracks={0: target_track.id},
        )

        assert result["placed"] == 0
        assert result["missing"] == [source_media.sha256]
        assert len(target.state.media) == 1
        assert target.state.track(target_track.id).clips == existing_clips
    finally:
        source.close()
        target.close()
