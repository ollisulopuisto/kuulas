from dataclasses import replace

from kuulas.changes import Change, diff
from kuulas.clock import frames_to_flicks
from kuulas.model import Clip, Media, Project, Track
from kuulas.ops import ripple_delete

RATE = 48_000


def media(media_id: str, digest: str) -> Media:
    return Media(media_id, f"{media_id}.wav", 1, 200_000, sha256=digest)


def speech_track(*clips: Clip) -> Track:
    return Track("track", "Voice", kind="speech", clips=clips)


def project(tracks, media_items) -> Project:
    return Project(rate=RATE, media=tuple(media_items), tracks=tuple(tracks))


def clip(clip_id, start, offset, length, *, media_id="m", gain_db=0.0) -> Clip:
    return Clip(clip_id, media_id, start, offset, length, gain_db=gain_db)


def test_diff_of_a_ripple_cut_is_one_removed_range():
    before = project([speech_track(clip("full", 0, 0, 10_000))], [media("m", "a" * 64)])

    result = diff(before, ripple_delete(before, 2_000, 4_000))

    assert result == (Change("removed", "a" * 64, frames_to_flicks(2_000, RATE),
                             frames_to_flicks(4_000, RATE)),)


def test_diff_survives_unrelated_later_edits():
    before = project([speech_track(clip("full", 0, 0, 10_000))], [media("m", "a" * 64)])
    cut = ripple_delete(before, 2_000, 4_000)
    # Later edits that change nothing audible: the tail moves elsewhere on
    # the timeline and its gain is raised.
    head, tail = cut.tracks[0].clips
    later = replace(cut, tracks=(replace(cut.tracks[0], clips=(
        head, replace(tail, start=5_000, gain_db=6.0))),))

    assert diff(before, later) == diff(before, cut)


def test_an_undone_cut_gives_no_changes():
    before = project([speech_track(clip("full", 0, 0, 10_000))], [media("m", "a" * 64)])
    # After an undo the audio is back; history restores the whole state, so
    # the restored range may sit in clips that merely touch in the source
    # and anywhere on the timeline.
    undone = project([speech_track(clip("first", 0, 0, 2_000),
                                   clip("second", 5_000, 2_000, 8_000))],
                     [media("m", "a" * 64)])

    assert diff(before, undone) == ()
    assert diff(undone, before) == ()


def test_restored_range_shows_as_added():
    cut = project([speech_track(clip("head", 0, 0, 2_000),
                                clip("tail", 2_000, 4_000, 6_000))],
                  [media("m", "a" * 64)])
    restored = project([speech_track(clip("full", 0, 0, 10_000))],
                       [media("m", "a" * 64)])

    result = diff(cut, restored)

    assert result == (Change("added", "a" * 64, frames_to_flicks(2_000, RATE),
                             frames_to_flicks(4_000, RATE)),)


def test_two_recordings_stay_separate():
    first, second = media("first", "a" * 64), media("second", "b" * 64)
    before = project([
        speech_track(clip("f", 0, 0, 10_000, media_id="first")),
        speech_track(clip("s", 0, 0, 10_000, media_id="second")),
    ], [first, second])
    # Cuts on each recording; the removed ranges overlap across recordings
    # and the second recording's first cut starts earlier than the first
    # recording's, so a change may never merge with or reorder another's.
    after = project([
        speech_track(clip("f-head", 0, 0, 2_000, media_id="first"),
                     clip("f-tail", 2_000, 4_000, 6_000, media_id="first")),
        speech_track(clip("s-head", 0, 0, 1_000, media_id="second"),
                     clip("s-mid", 1_000, 3_000, 2_000, media_id="second"),
                     clip("s-tail", 3_000, 6_000, 4_000, media_id="second")),
    ], [first, second])

    result = diff(before, after)

    assert result == (
        Change("removed", "a" * 64, frames_to_flicks(2_000, RATE),
               frames_to_flicks(4_000, RATE)),
        Change("removed", "b" * 64, frames_to_flicks(1_000, RATE),
               frames_to_flicks(3_000, RATE)),
        Change("removed", "b" * 64, frames_to_flicks(5_000, RATE),
               frames_to_flicks(6_000, RATE)),
    )
