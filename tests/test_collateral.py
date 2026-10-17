import pytest

from kuulas.clock import frames_to_flicks
from kuulas.collateral import Collateral, cut_collateral
from kuulas.model import Clip, Media, Project, Track
from kuulas.ops import EditError

RATE = 48_000


def media_items(*ids: str) -> tuple[Media, ...]:
    return tuple(Media(i, f"{i}.wav", 1, 10_000) for i in ids)


def track(track_id: str, *clips: Clip, mute: bool = False) -> Track:
    return Track(track_id, track_id, kind="speech", mute=mute, clips=clips)


def clip(clip_id: str, media_id: str, *, start: int = 0, offset: int = 0,
         length: int = 10_000, muted: bool = False) -> Clip:
    return Clip(clip_id, media_id, start, offset, length, muted=muted)


def project(*tracks: Track) -> Project:
    return Project(rate=RATE, media=media_items("ma", "mb", "mc"), tracks=tracks)


def transcript(*spans: tuple[str, int, int]) -> list[dict]:
    return [{"w": w, "s": frames_to_flicks(s, RATE), "e": frames_to_flicks(e, RATE)}
            for w, s, e in spans]


def ref(track_id: str, clip_id: str, index: int = 0) -> dict:
    return {"track": track_id, "clip": clip_id, "index": index}


def word(text: str, s: int, e: int, *, track_id: str, clip_id: str, media_id: str,
         index: int = 0, muted: bool = False) -> dict:
    """A word dict exactly as ``timeline_words`` gives it."""
    return {"w": text, "spk": "", "person": "", "s": s, "e": e, "track": track_id,
            "clip": clip_id, "media": media_id, "index": index, "muted": muted}


def test_no_overlap_gives_no_collateral():
    p = project(
        track("ta", clip("ca", "ma")),
        # The other track's clip and word sit entirely after the span.
        track("tb", clip("cb", "mb", start=3_000, length=7_000)),
    )
    transcripts = {"ma": transcript(("hello", 1_000, 2_000)),
                   "mb": transcript(("world", 1_000, 2_000))}

    result = cut_collateral(p, transcripts, [ref("ta", "ca")])

    assert result == Collateral(span=(1_000, 2_000), other_words=(), audio={})


def test_a_word_of_another_track_inside_the_span_is_found():
    p = project(
        track("ta", clip("ca", "ma")),
        track("tb", clip("cb", "mb")),
        # A clip that ends inside the span pins that audio reports the part
        # inside it, not the whole span.
        track("tc", clip("cc", "mc", length=1_600)),
    )
    transcripts = {
        "ma": transcript(("hello", 1_000, 2_000)),
        "mb": transcript(("sorry", 1_200, 1_800)),
        "mc": transcript(("cough", 1_200, 1_500)),
    }

    result = cut_collateral(p, transcripts, [ref("ta", "ca")])

    assert result == Collateral(
        span=(1_000, 2_000),
        other_words=(
            word("sorry", 1_200, 1_800, track_id="tb", clip_id="cb", media_id="mb"),
            word("cough", 1_200, 1_500, track_id="tc", clip_id="cc", media_id="mc"),
        ),
        audio={"tb": [(1_000, 2_000)], "tc": [(1_000, 1_600)]},
    )


def test_a_partly_overlapping_word_is_found_and_an_edge_touching_one_is_not():
    p = project(
        track("ta", clip("ca", "ma")),
        track("tb", clip("cb", "mb")),
    )
    transcripts = {
        "ma": transcript(("hello", 1_000, 2_000)),
        # "pre" ends at the span's start and "past" starts at its end: neither
        # shares a frame with it. "sorry" sticks out and still counts.
        "mb": transcript(("pre", 400, 1_000), ("sorry", 1_500, 2_500),
                         ("past", 2_000, 2_600)),
    }

    result = cut_collateral(p, transcripts, [ref("ta", "ca")])

    assert result == Collateral(
        span=(1_000, 2_000),
        other_words=(word("sorry", 1_500, 2_500, track_id="tb", clip_id="cb",
                          media_id="mb", index=1),),
        audio={"tb": [(1_000, 2_000)]},
    )


def test_muted_clips_and_tracks_are_reported_muted_but_not_in_audio():
    p = project(
        track("ta", clip("ca", "ma")),
        track("tb", clip("cb", "mb", muted=True)),
        track("tc", clip("cc", "mc"), mute=True),
    )
    transcripts = {
        "ma": transcript(("hello", 1_000, 2_000)),
        "mb": transcript(("sorry", 1_200, 1_800)),
        "mc": transcript(("cough", 1_300, 1_700)),
    }

    result = cut_collateral(p, transcripts, [ref("ta", "ca")])

    assert result == Collateral(
        span=(1_000, 2_000),
        other_words=(
            word("sorry", 1_200, 1_800, track_id="tb", clip_id="cb", media_id="mb",
                 muted=True),
            word("cough", 1_300, 1_700, track_id="tc", clip_id="cc", media_id="mc",
                 muted=True),
        ),
        audio={},
    )


def test_the_span_merges_two_adjacent_selected_words():
    p = project(
        track("ta", clip("ca", "ma")),
        # Two clips that meet inside the span: their audio merges into one
        # range, as the selected words' cover does.
        track("tb", clip("cb1", "mb", length=1_500),
              clip("cb2", "mb", start=1_500, offset=1_500, length=8_500)),
    )
    transcripts = {
        "ma": transcript(("hello", 1_000, 2_000), ("there", 2_000, 3_000)),
        "mb": transcript(("early", 0, 500), ("zap", 2_500, 2_800)),
    }

    result = cut_collateral(p, transcripts, [ref("ta", "ca"), ref("ta", "ca", 1)])

    assert result == Collateral(
        span=(1_000, 3_000),
        other_words=(word("zap", 2_500, 2_800, track_id="tb", clip_id="cb2",
                          media_id="mb", index=1),),
        audio={"tb": [(1_000, 3_000)]},
    )


def test_selected_words_are_never_in_other_words():
    p = project(
        # The selection spans two tracks; the third is the only other one.
        track("ta", clip("ca", "ma")),
        track("tb", clip("cb", "mb")),
        track("tc", clip("cc", "mc")),
    )
    transcripts = {
        "ma": transcript(("hello", 1_000, 2_000), ("later", 1_500, 2_500)),
        "mb": transcript(("sorry", 1_200, 1_800)),
        "mc": transcript(("cough", 1_300, 1_700)),
    }

    result = cut_collateral(p, transcripts, [ref("ta", "ca"), ref("tb", "cb")])

    assert result == Collateral(
        span=(1_000, 2_000),
        # "later" is not selected either, but it is on a selected track, so
        # it is not a word of another track.
        other_words=(word("cough", 1_300, 1_700, track_id="tc", clip_id="cc",
                          media_id="mc"),),
        # tb is selected, so its clip's audio is not collateral.
        audio={"tc": [(1_000, 2_000)]},
    )


def test_an_empty_or_stale_selection_is_refused():
    p = project(track("ta", clip("ca", "ma")))
    transcripts = {"ma": transcript(("hello", 1_000, 2_000))}

    with pytest.raises(EditError) as err:
        cut_collateral(p, transcripts, [])
    assert err.value.key == "error.edit.no_selection"

    with pytest.raises(EditError) as err:
        cut_collateral(p, transcripts, [ref("ta", "gone")])
    assert err.value.key == "error.edit.no_selection"
