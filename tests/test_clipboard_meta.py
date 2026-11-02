"""What a clipboard entry remembers (WP65 step 2): the metadata that later sorting
and searching read, so nothing has to be reconstructed from a project that may be gone."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas.clipboard import (
    ClipboardHistory,
    ClipRef,
    Entry,
    from_json,
    make_entry,
    make_entry_range,
    to_json,
)
from kuulas.clipboard_text import entry_text
from kuulas.model import Clip, Media, Project, Track
from kuulas.session import Session

RATE = 48_000
FLICKS = 705_600_000


def words(*items):
    """Transcript words: (text, start s, end s) -> the stored flicks form."""
    return [{"w": w, "s": round(s * FLICKS), "e": round(e * FLICKS), "spk": ""}
            for w, s, e in items]


def project():
    return Project(
        rate=RATE,
        media=(Media("ma", "anna.wav", 1, 400_000, sha256="a" * 64),
               Media("mb", "ville.wav", 1, 400_000, sha256="b" * 64)),
        tracks=(
            Track("ta", "Anna", kind="speech", clips=(
                Clip("a1", "ma", 0, 0, 96_000, gain_db=-3.0, fade_in=480),
                Clip("a2", "ma", 100_000, 200_000, 48_000, muted=True))),
            Track("tb", "Jingle", kind="music", clips=(
                Clip("b1", "mb", 0, 0, 96_000, gain_db=2.0),)),
        ),
    )


TRANSCRIPTS = {
    "ma": words(("Hello", 0.1, 0.4), ("there", 0.5, 0.9), ("friends", 1.2, 1.6),
                ("later", 4.2, 4.6), ("Words", 4.7, 4.9)),
    "mb": words(("lalala", 0.2, 0.8)),
}


# -- the data ------------------------------------------------------------------


def test_a_copy_records_tracks_media_and_does_not_carry_clip_mutes():
    got = make_entry(project(), ["a1", "a2", "b1"], now=1000.0)
    assert got.tracks == ("Anna", "Jingle")
    assert got.track_kinds == ("speech", "music")
    names = {ref.media_sha256[:1]: ref.media_name for ref in got.refs}
    assert names == {"a": "anna.wav", "b": "ville.wav"}
    muted = [ref.muted for ref in got.refs if ref.media_sha256[0] == "a"]
    assert sorted(muted) == [False, False]  # mute state belongs to the source timeline
    assert got.span == (0, 148_000)


def test_a_range_copy_records_the_same():
    got = make_entry_range(project(), 0, 50_000, ["tb"], now=1000.0)
    assert got.tracks == ("Jingle",)
    assert got.track_kinds == ("music",)
    assert got.refs[0].media_name == "ville.wav"


def test_the_new_fields_default_and_survive_json():
    bare = Entry("e1", "", 1.0)
    assert (bare.source_name, bare.source_id, bare.tracks, bare.track_kinds, bare.text,
            bare.shared, bare.adopted_from) == ("", "", (), (), "", False, "")
    full = Entry("e2", "n", 2.0, refs=(ClipRef("a" * 64, 0, 10, media_name="x.wav"),),
                 span=(0, 10), source_project="/p/One.kuulas", source_name="One",
                 source_id="abc", tracks=("Anna",), track_kinds=("speech",),
                 text="hello there", shared=True, adopted_from="/p/Two.kuulas")
    again = from_json(to_json(full))
    assert again == full
    assert again.refs[0].media_name == "x.wav"
    assert json.loads(to_json(full))["shared"] is True


def test_an_entry_from_before_loads_with_defaults():
    old = {"id": "e1", "name": "Old", "created_utc": 5.0, "span": [0, 100],
           "source_project": "/p/One.kuulas", "pinned": True,
           "refs": [{"media_sha256": "a" * 64, "offset": 0, "length": 100}],
           "tracks": ["Anna"]}  # the track names were an unknown key before
    history = ClipboardHistory.from_json(json.dumps({"entries": [old]}))
    (got,) = history.entries()
    assert got.tracks == ("Anna",)
    assert got.track_kinds == ()
    assert got.text == ""
    assert got.shared is False
    assert got.refs[0].media_name == ""
    assert got.extra == {}


def test_unknown_keys_are_still_kept():
    d = {"id": "e1", "name": "", "created_utc": 1.0, "future": {"x": 1}}
    assert json.loads(to_json(from_json(json.dumps(d))))["future"] == {"x": 1}


# -- the transcript text -------------------------------------------------------


def test_the_text_is_the_words_inside_the_copied_range_per_track():
    p = project()
    whole = make_entry(p, ["a1"], now=1.0)
    assert entry_text(p, whole, TRANSCRIPTS) == "Hello there friends"
    # a2 plays source 200_000.. = 4.17 s on: the later words
    second = make_entry(p, ["a2"], now=1.0)
    assert entry_text(p, second, TRANSCRIPTS) == "later Words"
    # two tracks: one line each, in track order
    both = make_entry(p, ["a1", "b1"], now=1.0)
    assert entry_text(p, both, TRANSCRIPTS) == "Hello there friends\nlalala"


def test_a_range_copy_takes_only_the_words_in_the_range():
    p = project()
    cut = make_entry_range(p, 24_000, 60_000, ["ta"], now=1.0)  # 0.5 s .. 1.25 s
    assert entry_text(p, cut, TRANSCRIPTS).split() == ["there"]


def test_no_transcript_means_no_text():
    p = project()
    assert entry_text(p, make_entry(p, ["a1"], now=1.0), {}) == ""
    assert entry_text(p, make_entry(p, ["a1"], now=1.0), {"ma": []}) == ""


# -- the session fills in the project ------------------------------------------


def wav(path: Path, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(RATE * 2) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Pilot.kuulas")
    s.import_media([str(wav(tmp_path / "a.wav", 1)), str(wav(tmp_path / "b.wav", 2))])
    yield s
    s.close()


def test_a_session_copy_records_the_project_and_the_text(session):
    for m in session.state.media:
        session.set_transcript(m.id, words(("one", 0.0, 0.4), ("two", 0.5, 0.9)), "t")
    a = session.state.tracks[0]
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]
    assert entry["source_project"] == str(session.package.path)
    assert entry["source_name"] == "Pilot"
    assert entry["source_id"] == session.package.manifest["id"]
    assert entry["tracks"] == [a.name]
    assert entry["track_kinds"] == [a.kind]
    assert entry["text"] == "one two"
    assert entry["shared"] is False
    assert entry["refs"][0]["media_name"] == "a.wav"
    # and it is what the file holds
    (stored,) = session.clipboard.load().entries()
    assert stored.text == "one two"


def test_a_cut_records_the_same(session):
    for m in session.state.media:
        session.set_transcript(m.id, words(("one", 0.0, 0.4), ("two", 1.0, 1.4)), "t")
    ids = [t.id for t in session.state.tracks]
    out = session.clipboard_cut(start=0, end=24_000, track_ids=ids)["clipboard"]
    (stored,) = session.clipboard.load().entries()
    assert out["entry"] == stored.id
    assert stored.text.split() == ["one", "one"]  # one per track, the first half second
    assert stored.source_name == "Pilot"
    assert stored.source_id == session.package.manifest["id"]
