from kuulas.clock import FLICKS, frames_to_flicks
from kuulas.model import Clip, Media, Project, Track
from kuulas.usage import Use, extract

RATE = 48_000


def media(media_id: str, digest: str, *, excerpt_of=None, excerpt_start=0) -> Media:
    return Media(media_id, f"{media_id}.wav", 1, 200_000, sha256=digest,
                 excerpt_of=excerpt_of, excerpt_start_flicks=excerpt_start)


def project(*, clips, automation=(), muted=False, media_items=None):
    track = Track("track", "Voice", kind="speech", mute=muted,
                  clips=tuple(clips), automation=tuple(automation))
    return Project(rate=RATE, media=tuple(media_items or [media("m", "a" * 64)]),
                   tracks=(track,))


def clip(clip_id, start, offset, length, *, media_id="m", muted=False):
    return Clip(clip_id, media_id, start, offset, length, muted=muted)


def test_cut_up_clips_map_to_recording_ranges_in_stable_order():
    state = project(clips=[clip("later", 20_000, 40_000, 10_000),
                           clip("first", 0, 5_000, 2_000)])

    result = extract(state, merge_gap=0)

    assert result == (
        Use("a" * 64, frames_to_flicks(5_000, RATE), frames_to_flicks(7_000, RATE),
            0, 2_000, "track", "speech", True),
        Use("a" * 64, frames_to_flicks(40_000, RATE), frames_to_flicks(50_000, RATE),
            20_000, 30_000, "track", "speech", True),
    )


def test_muted_clip_and_track_automation_below_minus_sixty_are_inaudible():
    state = project(
        clips=[clip("muted", 0, 0, 10_000, muted=True),
               clip("ducked", 20_000, 20_000, 10_000)],
        automation=((20_000, -80.0), (30_000, -80.0)),
    )

    result = extract(state, merge_gap=0)

    assert [use.audible for use in result] == [False, False]


def test_track_mute_makes_uses_inaudible():
    state = project(clips=[clip("piece", 0, 0, 100)], muted=True)

    use, = extract(state, merge_gap=0)

    assert use.audible is False


def test_automation_splits_at_the_minus_sixty_db_threshold():
    state = project(clips=[clip("piece", 0, 0, 100)], automation=((0, -80), (100, -40)))

    result = extract(state, merge_gap=0)

    assert [(use.timeline_from, use.timeline_to, use.audible) for use in result] == [
        (0, 50, False), (50, 100, True),
    ]


def test_excerpt_uses_original_recording_hash_and_clock_range():
    original = media("original", "b" * 64)
    excerpt = media("excerpt", "c" * 64, excerpt_of="original", excerpt_start=FLICKS * 3)
    state = project(clips=[clip("piece", 5_000, 100, 400, media_id="excerpt")],
                    media_items=[original, excerpt])

    use, = extract(state)

    assert use.media_sha256 == "b" * 64
    assert use.from_flicks == 3 * FLICKS + frames_to_flicks(100, RATE)
    assert use.to_flicks == 3 * FLICKS + frames_to_flicks(500, RATE)
    assert (use.timeline_from, use.timeline_to) == (5_000, 5_400)


def test_uses_with_short_source_gap_merge():
    state = project(clips=[clip("one", 0, 0, RATE),
                           clip("two", RATE + 100, RATE + 100, RATE)])

    result = extract(state, merge_gap=frames_to_flicks(101, RATE))

    assert len(result) == 1
    assert result[0].from_flicks == 0
    assert result[0].to_flicks == frames_to_flicks(2 * RATE + 100, RATE)
    assert (result[0].timeline_from, result[0].timeline_to) == (0, 2 * RATE + 100)


def test_same_state_has_identical_result():
    state = project(clips=[clip("b", 10, 20, 5), clip("a", 0, 0, 5)])

    assert extract(state) == extract(state)
