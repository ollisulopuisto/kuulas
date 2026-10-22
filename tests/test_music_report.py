import threading
from dataclasses import replace

import numpy as np
import pytest

from kuulas import messages
from kuulas import music_report as module
from kuulas.model import Clip, Media, Project, Track
from kuulas.music_report import (
    MusicReportError,
    ReportRow,
    build_report,
    render_csv,
    render_html,
)
from kuulas.session import Session

RATE = 48_000


class MemoryStore:
    def __init__(self, arrays: dict[str, np.ndarray]):
        self.arrays = arrays

    def read(self, media_id: str, first: int, count: int) -> np.ndarray:
        source = self.arrays[media_id]
        out = np.zeros((source.shape[0], count), dtype=np.float32)
        lo, hi = max(0, first), min(source.shape[1], first + count)
        if hi > lo:
            out[:, lo - first:hi - first] = source[:, lo:hi]
        return out


def make_report(project: Project, arrays: dict[str, np.ndarray] | None = None):
    return build_report(project, MemoryStore(arrays or {}))


def speech_then_silence(seconds: int, *, active_seconds: int = 2) -> np.ndarray:
    audio = np.zeros(seconds * RATE, dtype=np.float32)
    audio[:active_seconds * RATE] = 0.3 * np.random.default_rng(2).standard_normal(
        active_seconds * RATE)
    return audio


def media(media_id: str, digest: str, *, name: str | None = None,
          music_info: dict | None = None) -> Media:
    extra: dict = {}
    if music_info is not None:
        extra["music_info"] = music_info
    return Media(media_id, name or f"{media_id}.wav", 2, 200_000, sha256=digest,
                 extra=extra)


def clip(clip_id: str, start: int, offset: int, length: int, *,
         media_id: str = "m", muted: bool = False) -> Clip:
    return Clip(clip_id, media_id, start, offset, length, muted=muted)


def track(track_id: str, kind: str, clips, automation=(), muted: bool = False
          ) -> Track:
    return Track(track_id, "Music" if kind == "music" else "Speech", kind=kind,
                 clips=tuple(clips), automation=tuple(automation), mute=muted)


def state(*, media_items, tracks, **kw) -> Project:
    return Project(rate=RATE, media=tuple(media_items), tracks=tuple(tracks), **kw)


def test_report_lists_each_music_use_with_programme_times():
    m1 = media("m1", "a" * 64, name="Bed one.wav",
               music_info={"title": "Bed One", "artist": "The Artist"})
    m2 = media("m2", "b" * 64, name="Bed two.wav",
               music_info={"title": "Bed Two", "artist": "The Artist"})
    s = state(
        media_items=[m1, m2],
        tracks=[track("t1", "music", [
            clip("c1", 0, 0, RATE, media_id="m1"),
            clip("c2", RATE, 0, RATE, media_id="m2"),
        ])])

    report = make_report(s)

    assert [r.order for r in report] == [1, 2]
    assert [r.title for r in report] == ["Bed One", "Bed Two"]
    assert [r.artist for r in report] == ["The Artist", "The Artist"]
    assert [r.in_time for r in report] == ["00:00:00", "00:00:01"]
    assert [r.out_time for r in report] == ["00:00:01", "00:00:02"]
    assert [r.duration for r in report] == ["00:00:01", "00:00:01"]
    assert [r.file_name for r in report] == ["Bed one.wav", "Bed two.wav"]
    assert [r.background for r in report] == [False, False]


def test_muted_and_silenced_music_is_not_reported():
    m = media("m", "a" * 64, music_info={"title": "Bed", "artist": "A"})
    s = state(
        media_items=[m],
        tracks=[track("t1", "music", [
            clip("muted", 0, 0, RATE, media_id="m", muted=True),
            clip("ducked", RATE, 0, RATE, media_id="m"),
        ], automation=((RATE, -80.0), (2 * RATE, -80.0)))])

    report = make_report(s)

    assert report == ()


def test_a_short_sting_is_reported_as_one_whole_second():
    m = media("m", "a" * 64, music_info={"title": "Sting", "artist": "A"})
    s = state(
        media_items=[m],
        tracks=[track("t1", "music", [
            clip("c", 0, 0, int(0.4 * RATE), media_id="m")])])

    [row] = make_report(s)

    assert (row.in_time, row.out_time, row.duration) == (
        "00:00:00", "00:00:01", "00:00:01")


def test_duration_rounds_up_and_in_out_stay_consistent():
    # Starts 0.9 s into the minute and lasts 0.2 s: the start is floored, the
    # duration rounded up, and the out time is start plus duration, so the
    # three columns always agree with each other.
    m = media("m", "a" * 64, music_info={"title": "Sting", "artist": "A"})
    start = 59 * RATE + int(0.9 * RATE)
    s = state(
        media_items=[m],
        tracks=[track("t1", "music", [
            clip("c", start, 0, int(0.2 * RATE), media_id="m")])])

    [row] = make_report(s)

    assert (row.in_time, row.out_time, row.duration) == (
        "00:00:59", "00:01:00", "00:00:01")


def test_pieces_of_one_track_merge_across_short_gaps():
    m = media("m", "a" * 64, music_info={"title": "Bed", "artist": "A"})
    s = state(
        media_items=[m],
        tracks=[track("t1", "music", [
            clip("one", 0, 0, RATE, media_id="m"),
            clip("two", RATE + 100, RATE + 100, RATE - 100, media_id="m"),
        ])])

    report = make_report(s)

    assert len(report) == 1
    assert report[0].title == "Bed"
    assert report[0].in_time == "00:00:00"
    assert report[0].out_time == "00:00:02"
    assert report[0].duration == "00:00:02"


def test_music_under_speech_is_marked_background():
    frames = 4 * RATE
    m_speech = Media("s", "speech.wav", 1, frames, sha256="s" * 64)
    m_music = media("mu", "u" * 64, music_info={"title": "Bed", "artist": "A"})
    s = state(
        media_items=[m_speech, m_music],
        tracks=[
            track("t1", "speech", [clip("sp", 0, 0, frames, media_id="s")]),
            track("t2", "music", [
                clip("under", RATE // 2, 0, RATE, media_id="mu"),
                clip("alone", 3 * RATE, 0, RATE, media_id="mu"),
            ]),
        ])

    report = make_report(s, {"s": speech_then_silence(4)[None, :]})

    assert [r.background for r in report] == [True, False]


def test_music_in_a_speech_clip_silent_gap_is_featured():
    seconds = 10
    frames = seconds * RATE
    rng = np.random.default_rng(4)
    speech = np.zeros(frames, dtype=np.float32)
    for start in (0, 6 * RATE):
        speech[start:start + 2 * RATE] = 0.3 * rng.standard_normal(2 * RATE)
    m_speech = Media("s", "speech.wav", 1, frames, sha256="s" * 64)
    m_music = media("mu", "u" * 64,
                    music_info={"title": "Bed", "artist": "A"})
    s = state(
        media_items=[m_speech, m_music],
        tracks=[
            track("t1", "speech", [clip("sp", 0, 0, frames, media_id="s")]),
            track("t2", "music", [
                clip("under", RATE // 2, 0, RATE, media_id="mu"),
                clip("gap", 4 * RATE, RATE, RATE, media_id="mu"),
            ]),
        ],
    )
    store = MemoryStore({"s": speech[None, :]})

    report = build_report(s, store)

    assert [row.background for row in report] == [True, False]


def test_muted_speech_does_not_make_music_background():
    frames = 4 * RATE
    m_speech = Media("s", "speech.wav", 1, frames, sha256="s" * 64)
    m_music = media("mu", "u" * 64,
                    music_info={"title": "Bed", "artist": "A"})
    s = state(
        media_items=[m_speech, m_music],
        tracks=[
            track("t1", "speech", [clip("sp", 0, 0, frames, media_id="s")],
                  muted=True),
            track("t2", "music", [clip("under", RATE // 2, 0, RATE, media_id="mu")]),
        ],
    )

    report = make_report(s, {"s": speech_then_silence(4)[None, :]})

    assert [row.background for row in report] == [False]


def test_one_muted_track_of_a_speaker_does_not_hide_the_others():
    frames = 4 * RATE
    m_speech = Media("s", "speech.wav", 1, frames, sha256="s" * 64)
    m_music = media("mu", "u" * 64,
                    music_info={"title": "Bed", "artist": "A"})
    muted = replace(track("t1", "speech", [clip("a", 0, 0, frames, media_id="s")],
                          muted=True), speaker="Ann")
    audible = replace(track("t2", "speech", [clip("b", 0, 0, frames, media_id="s")]),
                      speaker="Ann")
    s = state(
        media_items=[m_speech, m_music],
        tracks=[muted, audible,
                track("t3", "music", [clip("under", RATE // 2, 0, RATE, media_id="mu")])],
    )

    report = make_report(s, {"s": speech_then_silence(4)[None, :]})

    assert [row.background for row in report] == [True]


def test_missing_metadata_is_flagged():
    m = media("m", "a" * 64, name="no tags.wav")
    s = state(
        media_items=[m],
        tracks=[track("t1", "music", [clip("c", 0, 0, RATE, media_id="m")])])

    report = make_report(s)

    assert len(report) == 1
    assert report[0].missing_metadata is True
    assert report[0].title == ""
    assert report[0].artist == ""


def test_csv_is_semicolon_separated_utf8():
    m = media("m", "a" * 64, name="Biisi.wav",
              music_info={"title": "Biisi", "artist": "Taiteilija"})
    s = state(
        media_items=[m],
        tracks=[track("t1", "music", [clip("c", 0, 0, RATE, media_id="m")])])

    text = render_csv(make_report(s))

    lines = text.removeprefix("\ufeff").splitlines()
    assert lines[0] == ("Order;Title;Artist;Composer;Publisher;ISRC;File name;"
                        "In;Out;Duration;Use;Metadata")
    assert lines[1] == ("1;Biisi;Taiteilija;;;;Biisi.wav;"
                        "00:00:00;00:00:01;00:00:01;Featured;")
    text.encode("utf-8")  # must be encodable as UTF-8


def test_csv_has_utf8_bom_and_missing_metadata_flag():
    m = media("m", "a" * 64, name="Äiti.wav")
    s = state(media_items=[m], tracks=[track("t", "music", [clip("c", 0, 0, RATE)])])

    data = render_csv(make_report(s)).encode("utf-8")

    assert data.startswith(b"\xef\xbb\xbf")
    assert "missing" in data.decode("utf-8-sig").lower()
    assert "Äiti.wav" in data.decode("utf-8-sig")


def test_render_html_contains_each_row():
    frames = 4 * RATE
    m = Media("m", "Bed.wav", 1, frames, sha256="a" * 64,
              extra={"music_info": {"title": "Bed", "artist": "A", "isrc": "ISRC123"}})
    s = state(
        media_items=[m],
        tracks=[track("t1", "music", [clip("c", 0, 0, RATE, media_id="m")]),
                track("t2", "speech", [clip("sp", 0, 0, frames, media_id="m")])])

    html = render_html(make_report(s, {"m": speech_then_silence(4)[None, :]}))

    assert "Bed" in html
    assert "A" in html
    assert "ISRC123" in html
    assert "background" in html.lower()


def test_html_localizes_report_text_and_marks_missing_metadata():
    m = media("m", "a" * 64)
    s = state(media_items=[m], tracks=[track("t", "music", [clip("c", 0, 0, RATE)])])
    messages.set_language("fi")
    try:
        rendered = render_html(make_report(s))
    finally:
        messages.set_language("en")

    assert '<html lang="fi">' in rendered
    assert "Musiikkiraportti" in rendered
    assert "Nimi tai esittäjä puuttuu" in rendered


def test_csv_localizes_headings_and_background_labels():
    messages.set_language("fi")
    try:
        rendered = render_csv((ReportRow(
            1, "Ääni", "Esiintyjä", "", "", "", "Ääni.wav", "00:00:00",
            "00:00:01", "00:00:01", True, True),))
    finally:
        messages.set_language("en")

    assert "Järjestys;Nimi;Esittäjä" in rendered
    assert "Taustalla" in rendered
    assert "Nimi tai esittäjä puuttuu" in rendered


def test_report_row_is_a_dataclass():
    r = ReportRow(1, "T", "Ar", "Co", "Pu", "ISRC", "f.wav",
                  "00:00:00", "00:01:00", "00:01:00", False, False)
    assert (r.order, r.title, r.background, r.missing_metadata) == (
        1, "T", False, False)


def test_csv_guards_formula_cells_with_single_quote():
    row = ReportRow(
        order=1,
        title="=SUM(A1)",
        artist="+Artist",
        composer="-Bach",
        publisher="@Publisher",
        isrc="=ISRC123",
        file_name="track.wav",
        in_time="00:00:00",
        out_time="00:00:01",
        duration="00:00:01",
        background=False,
        missing_metadata=False,
    )
    text = render_csv((row,))
    lines = text.removeprefix("\ufeff").splitlines()
    assert lines[1] == ("1;'=SUM(A1);'+Artist;'-Bach;'@Publisher;'=ISRC123;track.wav;"
                        "00:00:00;00:00:01;00:00:01;Featured;")


def test_session_music_report_formats(tmp_path):
    s = Session(tmp_path / "Proj.kuulas")
    try:
        # Default returns tuple of ReportRow
        rows = s.music_report()
        assert isinstance(rows, tuple)

        # JSON format returns list of dicts
        data = s.music_report(format="json")
        assert isinstance(data, list)

        # CSV format returns string with BOM
        csv_data = s.music_report(format="csv")
        assert isinstance(csv_data, str)
        assert csv_data.startswith("\ufeff")

        # HTML format returns html string
        html_data = s.music_report(format="html")
        assert isinstance(html_data, str)
        assert "<html" in html_data

        # Invalid format raises MusicReportError
        with pytest.raises(MusicReportError) as exc_info:
            s.music_report(format="pdf")
        assert exc_info.value.key == "error.music_report.bad_format"
    finally:
        s.close()


def test_building_the_report_does_not_hold_the_session_lock(tmp_path, monkeypatch):
    # The report runs speech analysis, which can take seconds on a long
    # project. It must not block edits meanwhile (ground rule 14), so the
    # session lock must be free while the report is being built.
    s = Session(tmp_path / "Proj.kuulas")
    free = []

    def build_and_probe(project, store, span=None):
        def try_lock():
            got = s.lock.acquire(timeout=1.0)
            if got:
                s.lock.release()
            free.append(got)

        other = threading.Thread(target=try_lock)
        other.start()
        other.join()
        return ()

    monkeypatch.setattr(module, "build_report", build_and_probe)
    try:
        s.music_report(format="csv")
    finally:
        s.close()
    assert free == [True]


def _two_pieces() -> Project:
    info = {"artist": "A"}
    m1 = media("m1", "a" * 64, name="Bed one.wav", music_info={**info, "title": "One"})
    m2 = media("m2", "b" * 64, name="Bed two.wav", music_info={**info, "title": "Two"})
    return state(media_items=[m1, m2], tracks=[track("t1", "music", [
        clip("c1", 0, 0, 2 * RATE, media_id="m1"),
        clip("c2", 4 * RATE, 0, 2 * RATE, media_id="m2"),
    ])])


def test_report_of_a_range_lists_only_music_heard_in_it():
    rows = build_report(_two_pieces(), MemoryStore({}), span=(3 * RATE, 7 * RATE))
    assert [r.title for r in rows] == ["Two"]
    assert [r.order for r in rows] == [1]


def test_report_of_a_range_cuts_a_piece_at_the_range_edges():
    rows = build_report(_two_pieces(), MemoryStore({}), span=(RATE, 5 * RATE))
    assert [(r.title, r.in_time, r.out_time, r.duration) for r in rows] == [
        ("One", "00:00:01", "00:00:02", "00:00:01"),
        ("Two", "00:00:04", "00:00:05", "00:00:01"),
    ]


def test_session_music_report_takes_a_range(tmp_path):
    s = Session(tmp_path / "Proj.kuulas")
    try:
        assert s.music_report(format="json", span=(0, RATE)) == []
        with pytest.raises(MusicReportError) as exc_info:
            s.music_report(span=(5, 5))
        assert exc_info.value.key == "error.music_report.bad_range"
    finally:
        s.close()
