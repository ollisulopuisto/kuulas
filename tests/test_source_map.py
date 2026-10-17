"""Tests for the source map: where a recording is used on the timeline."""

from __future__ import annotations

from kuulas.clock import FLICKS, frames_to_flicks
from kuulas.model import Clip, Media, Project, Track
from kuulas.source_map import coverage, part_numbers, recording_clips

RATE = 48_000


def _media(media_id: str, digest: str, *, frames: int = 200_000,
           excerpt_of: str | None = None, excerpt_start: int = 0) -> Media:
    return Media(media_id, f"{media_id}.wav", 1, frames, sha256=digest,
                 excerpt_of=excerpt_of, excerpt_start_flicks=excerpt_start)


def _clip(clip_id: str, start: int, offset: int, length: int,
          *, media_id: str = "m", muted: bool = False) -> Clip:
    return Clip(clip_id, media_id, start, offset, length, muted=muted)


def _project(*, media_items, clips_by_track, muted_tracks=()):
    tracks = []
    for index, clips in enumerate(clips_by_track):
        track_id = f"t{index + 1}"
        tracks.append(Track(track_id, f"Track {index + 1}",
                            mute=track_id in muted_tracks,
                            clips=tuple(clips)))
    return Project(rate=RATE, media=tuple(media_items), tracks=tuple(tracks))


class TestRecordingClips:
    def test_one_clip(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE)],
            clips_by_track=[[_clip("c1", 0, 0, RATE)]],
        )

        assert recording_clips(state, "a" * 64) == [
            ("t1", "c1", 0, frames_to_flicks(RATE, RATE), False),
        ]

    def test_sorted_by_source_start_then_track_order(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE * 2)],
            clips_by_track=[
                [_clip("later", 0, RATE, RATE)],
                [_clip("earlier", 0, 0, RATE)],
            ],
        )

        assert recording_clips(state, "a" * 64) == [
            ("t2", "earlier", 0, frames_to_flicks(RATE, RATE), False),
            ("t1", "later", frames_to_flicks(RATE, RATE),
             frames_to_flicks(RATE * 2, RATE), False),
        ]

    def test_muted_flag_is_clip_muted(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE)],
            clips_by_track=[[_clip("c1", 0, 0, RATE, muted=True)]],
        )

        assert recording_clips(state, "a" * 64) == [
            ("t1", "c1", 0, frames_to_flicks(RATE, RATE), True),
        ]

    def test_excerpt_counts_as_original_recording(self):
        original = _media("original", "b" * 64, frames=RATE)
        excerpt = _media("excerpt", "c" * 64, frames=RATE // 2,
                         excerpt_of="original", excerpt_start=FLICKS * 2)
        state = _project(
            media_items=[original, excerpt],
            clips_by_track=[[_clip("piece", 0, 100, 400, media_id="excerpt")]],
        )

        assert recording_clips(state, "b" * 64) == [
            ("t1", "piece", 2 * FLICKS + frames_to_flicks(100, RATE),
             2 * FLICKS + frames_to_flicks(500, RATE), False),
        ]

    def test_missing_recording_gives_empty_list(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE)],
            clips_by_track=[[_clip("c1", 0, 0, RATE)]],
        )

        assert recording_clips(state, "z" * 64) == []


class TestCoverage:
    def test_one_clip_leaves_unused_tail(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE * 2)],
            clips_by_track=[[_clip("c1", 0, 0, RATE)]],
        )

        used, cut, unused = coverage(state, "a" * 64)

        assert used == [(0, frames_to_flicks(RATE, RATE))]
        assert cut == []
        assert unused == [(frames_to_flicks(RATE, RATE),
                           frames_to_flicks(RATE * 2, RATE))]

    def test_split_with_muted_middle_gives_used_cut_used(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE * 3)],
            clips_by_track=[
                [_clip("a", 0, 0, RATE),
                 _clip("b", RATE, RATE, RATE, muted=True),
                 _clip("c", RATE * 2, RATE * 2, RATE)],
            ],
        )

        used, cut, unused = coverage(state, "a" * 64)

        assert used == [
            (0, frames_to_flicks(RATE, RATE)),
            (frames_to_flicks(RATE * 2, RATE),
             frames_to_flicks(RATE * 3, RATE)),
        ]
        assert cut == [(frames_to_flicks(RATE, RATE),
                        frames_to_flicks(RATE * 2, RATE))]
        assert unused == []

    def test_two_tracks_same_stretch_merge_to_one_used_range(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE)],
            clips_by_track=[
                [_clip("a", 0, 0, RATE)],
                [_clip("b", 0, 0, RATE)],
            ],
        )

        used, cut, unused = coverage(state, "a" * 64)

        assert used == [(0, frames_to_flicks(RATE, RATE))]
        assert cut == []
        assert unused == []

    def test_track_mute_is_cut(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE)],
            clips_by_track=[[_clip("a", 0, 0, RATE)]],
            muted_tracks=("t1",),
        )

        used, cut, unused = coverage(state, "a" * 64)

        assert used == []
        assert cut == [(0, frames_to_flicks(RATE, RATE))]
        assert unused == []

    def test_missing_recording_gives_empty_coverage(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE)],
            clips_by_track=[[_clip("c1", 0, 0, RATE)]],
        )

        assert coverage(state, "z" * 64) == ([], [], [])


class TestPartNumbers:
    def test_one_clip_is_part_one_of_one(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE)],
            clips_by_track=[[_clip("c1", 0, 0, RATE)]],
        )

        assert part_numbers(state, "a" * 64) == {"c1": (1, 1)}

    def test_part_numbers_follow_source_order_not_track_order(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE * 2)],
            clips_by_track=[
                [_clip("second", 0, RATE, RATE)],
                [_clip("first", 0, 0, RATE)],
            ],
        )

        assert part_numbers(state, "a" * 64) == {
            "first": (1, 2),
            "second": (2, 2),
        }

    def test_missing_recording_gives_empty_dict(self):
        state = _project(
            media_items=[_media("m", "a" * 64, frames=RATE)],
            clips_by_track=[[_clip("c1", 0, 0, RATE)]],
        )

        assert part_numbers(state, "z" * 64) == {}
