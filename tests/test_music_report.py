from kuulas import messages
from kuulas.model import Clip, Media, Project, Track
from kuulas.music_report import ReportRow, build_report, render_csv, render_html

RATE = 48_000


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

    report = build_report(s)

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

    report = build_report(s)

    assert report == ()


def test_pieces_of_one_track_merge_across_short_gaps():
    m = media("m", "a" * 64, music_info={"title": "Bed", "artist": "A"})
    s = state(
        media_items=[m],
        tracks=[track("t1", "music", [
            clip("one", 0, 0, RATE, media_id="m"),
            clip("two", RATE + 100, RATE + 100, RATE, media_id="m"),
        ])])

    report = build_report(s)

    assert len(report) == 1
    assert report[0].title == "Bed"
    assert report[0].in_time == "00:00:00"
    assert report[0].out_time == "00:00:02"
    assert report[0].duration == "00:00:02"


def test_music_under_speech_is_marked_background():
    m_speech = media("s", "s" * 64)
    m_music = media("mu", "u" * 64, music_info={"title": "Bed", "artist": "A"})
    s = state(
        media_items=[m_speech, m_music],
        tracks=[
            track("t1", "speech", [clip("sp", 0, 0, RATE, media_id="s")]),
            track("t2", "music", [
                clip("under", RATE // 2, 0, RATE, media_id="mu"),
                clip("alone", 2 * RATE, 0, RATE, media_id="mu"),
            ]),
        ])

    report = build_report(s)

    assert [r.background for r in report] == [True, False]


def test_missing_metadata_is_flagged():
    m = media("m", "a" * 64, name="no tags.wav")
    s = state(
        media_items=[m],
        tracks=[track("t1", "music", [clip("c", 0, 0, RATE, media_id="m")])])

    report = build_report(s)

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

    text = render_csv(build_report(s))

    lines = text.removeprefix("\ufeff").splitlines()
    assert lines[0] == ("Order;Title;Artist;Composer;Publisher;ISRC;File name;"
                        "In;Out;Duration;Use;Metadata")
    assert lines[1] == ("1;Biisi;Taiteilija;;;;Biisi.wav;"
                        "00:00:00;00:00:01;00:00:01;Featured;")
    text.encode("utf-8")  # must be encodable as UTF-8


def test_csv_has_utf8_bom_and_missing_metadata_flag():
    m = media("m", "a" * 64, name="Äiti.wav")
    s = state(media_items=[m], tracks=[track("t", "music", [clip("c", 0, 0, RATE)])])

    data = render_csv(build_report(s)).encode("utf-8")

    assert data.startswith(b"\xef\xbb\xbf")
    assert "missing" in data.decode("utf-8-sig").lower()
    assert "Äiti.wav" in data.decode("utf-8-sig")


def test_render_html_contains_each_row():
    m = media("m", "a" * 64, name="Bed.wav",
              music_info={"title": "Bed", "artist": "A", "isrc": "ISRC123"})
    s = state(
        media_items=[m],
        tracks=[track("t1", "music", [clip("c", 0, 0, RATE, media_id="m")]),
                track("t2", "speech", [clip("sp", 0, 0, RATE, media_id="m")])])

    html = render_html(build_report(s))

    assert "Bed" in html
    assert "A" in html
    assert "ISRC123" in html
    assert "background" in html.lower()


def test_html_localizes_report_text_and_marks_missing_metadata():
    m = media("m", "a" * 64)
    s = state(media_items=[m], tracks=[track("t", "music", [clip("c", 0, 0, RATE)])])
    messages.set_language("fi")
    try:
        rendered = render_html(build_report(s))
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
