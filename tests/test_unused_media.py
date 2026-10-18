from kuulas.clock import frames_to_flicks
from kuulas.model import Clip, Media, Project, Track
from kuulas.unused_media import unused_media, usage_summary

RATE = 48_000


def media(media_id: str, digest: str, *, excerpt_of=None,
          excerpt_start=0) -> Media:
    return Media(media_id, f"{media_id}.wav", 1, 200_000, sha256=digest,
                 excerpt_of=excerpt_of, excerpt_start_flicks=excerpt_start)


def clip(clip_id, start, offset, length, *, media_id="m", muted=False) -> Clip:
    return Clip(clip_id, media_id, start, offset, length, muted=muted)


def track(*clips, track_id="track", gate=(), mute=False, automation=()) -> Track:
    return Track(track_id, "Voice", kind="speech", mute=mute, clips=clips,
                 gate=tuple(gate), automation=tuple(automation))


def project(*tracks, media_items) -> Project:
    return Project(rate=RATE, media=tuple(media_items), tracks=tracks)


def test_a_media_never_placed_is_unused():
    state = project(track(clip("piece", 0, 0, 10_000)),
                    media_items=[media("orphan", "b" * 64),
                                 media("m", "a" * 64)])

    assert unused_media(state) == ("orphan",)
    assert usage_summary(state)["orphan"] == {
        "clips": 0, "audible_clips": 0, "audible_flicks": 0}
    assert usage_summary(state)["m"] == {
        "clips": 1, "audible_clips": 1,
        "audible_flicks": frames_to_flicks(10_000, RATE)}


def test_a_media_only_on_a_muted_clip_is_unused():
    state = project(track(clip("silent", 0, 0, 10_000, muted=True)),
                    media_items=[media("m", "a" * 64)])

    assert unused_media(state) == ("m",)
    assert usage_summary(state)["m"] == {
        "clips": 1, "audible_clips": 0, "audible_flicks": 0}


def test_a_media_inside_a_closed_gate_only_is_unused():
    state = project(track(clip("gated", 0, 0, 10_000), gate=((0, 10_000),)),
                    media_items=[media("m", "a" * 64)])

    assert unused_media(state) == ("m",)
    assert usage_summary(state)["m"] == {
        "clips": 1, "audible_clips": 0, "audible_flicks": 0}


def test_a_partly_gated_media_is_used_for_the_open_part():
    state = project(track(clip("half", 0, 0, 10_000), gate=((5_000, 10_000),)),
                    media_items=[media("m", "a" * 64)])

    assert unused_media(state) == ()
    assert usage_summary(state)["m"] == {
        "clips": 1, "audible_clips": 1,
        "audible_flicks": frames_to_flicks(5_000, RATE)}


def test_two_clips_of_one_media_count_the_audible_one():
    state = project(track(clip("silent", 0, 0, 10_000, muted=True),
                          clip("heard", 20_000, 20_000, 10_000)),
                    media_items=[media("m", "a" * 64)])

    assert unused_media(state) == ()
    assert usage_summary(state)["m"] == {
        "clips": 2, "audible_clips": 1,
        "audible_flicks": frames_to_flicks(10_000, RATE)}


def test_an_empty_project_has_no_media():
    state = Project()

    assert unused_media(state) == ()
    assert usage_summary(state) == {}


def test_a_media_on_a_muted_track_is_unused():
    state = project(track(clip("piece", 0, 0, 10_000), mute=True),
                    media_items=[media("m", "a" * 64)])

    assert unused_media(state) == ("m",)
    assert usage_summary(state)["m"] == {
        "clips": 1, "audible_clips": 0, "audible_flicks": 0}


def test_a_media_ducked_below_minus_sixty_db_is_unused():
    state = project(track(clip("ducked", 0, 0, 10_000),
                          automation=((0, -80.0), (10_000, -80.0))),
                    media_items=[media("m", "a" * 64)])

    assert unused_media(state) == ("m",)
    assert usage_summary(state)["m"] == {
        "clips": 1, "audible_clips": 0, "audible_flicks": 0}


def test_adjacent_pieces_of_one_split_both_count():
    # A split makes two clips that touch; extract would merge their uses into
    # one at the default merge gap, and the merged use's start lies in the
    # first clip only. merge_gap=0 keeps them apart so both count.
    state = project(track(clip("head", 0, 0, 10_000),
                          clip("tail", 10_000, 10_000, 10_000)),
                    media_items=[media("m", "a" * 64)])

    assert unused_media(state) == ()
    assert usage_summary(state)["m"] == {
        "clips": 2, "audible_clips": 2,
        "audible_flicks": frames_to_flicks(20_000, RATE)}


def test_an_original_whose_excerpt_alone_plays_stays_unused():
    # The task counts per media id: "no clip references it at all" leaves the
    # original unused even when an excerpt of it plays.
    state = project(
        track(clip("cut", 0, 1_000, 10_000, media_id="excerpt")),
        media_items=[media("orig", "a" * 64),
                    media("excerpt", "b" * 64, excerpt_of="orig",
                          excerpt_start=frames_to_flicks(1_000, RATE))])

    assert unused_media(state) == ("orig",)
    assert usage_summary(state)["orig"] == {
        "clips": 0, "audible_clips": 0, "audible_flicks": 0}
    assert usage_summary(state)["excerpt"] == {
        "clips": 1, "audible_clips": 1,
        "audible_flicks": frames_to_flicks(10_000, RATE)}
