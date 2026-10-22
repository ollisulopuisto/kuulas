"""Music report (WP25): every piece of music the programme actually plays.

Reads :func:`kuulas.usage.extract`'s music-track uses, joins each to its
media's ffprobe tags (stored at import in ``Media.extra["music_info"]``),
and emits a semicolon-separated UTF-8 CSV and a printable HTML table for
Teosto/Gramex-style royalty reporting.
"""

from __future__ import annotations

import csv
import html
import io
from dataclasses import dataclass

import numpy as np

from . import analysis
from .messages import KuulasError, t
from .mixer import Store
from .model import Media, Project
from .usage import extract

_HEADER_KEYS = ("order", "title", "artist", "composer", "publisher", "isrc",
                "file_name", "in", "out", "duration", "usage", "metadata")


class MusicReportError(KuulasError):
    """A problem building or formatting the music report."""


@dataclass(frozen=True)
class ReportRow:
    """One music use, ready for a report row."""

    order: int
    title: str
    artist: str
    composer: str
    publisher: str
    isrc: str
    file_name: str
    in_time: str
    out_time: str
    duration: str
    background: bool
    missing_metadata: bool


def _stamp(seconds: int) -> str:
    """Whole ``seconds`` as ``hh:mm:ss``."""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _speech_activity(project: Project, store: Store) -> tuple[tuple[int, int], ...]:
    """Timeline ranges where an audible speech lane has detected activity.

    ``speech_lanes`` already leaves muted tracks out."""
    hop = analysis.hop_frames(project.rate)
    ranges: list[tuple[int, int]] = []
    for lane in analysis.speech_lanes(project, store).speakers:
        on = np.asarray(lane.on, dtype=bool)
        starts = np.flatnonzero(on & np.r_[True, ~on[:-1]])
        ends = np.flatnonzero(on & np.r_[~on[1:], True]) + 1
        ranges.extend(
            (start * hop, min(end * hop, project.length))
            for start, end in zip(starts, ends, strict=True)
        )
    return tuple(ranges)


def build_report(project: Project, store: Store,
                 span: tuple[int, int] | None = None) -> tuple[ReportRow, ...]:
    """Every audible music-track use, in timeline order, with its metadata.

    With ``span`` (timeline frames, start below end) only the music heard inside it
    is listed, each piece cut at the span's edges, as the exported excerpt plays it;
    times stay the programme's own (an export of the selection reports the selection).

    A piece is *background* when it overlaps detected speech activity on
    another track, otherwise *featured*. A row is missing its title or artist
    when the media has no tags for them.
    """
    uses = extract(project)
    media_by_sha = {m.sha256: m for m in project.media}
    rate = project.rate
    speech = _speech_activity(project, store)
    rows: list[ReportRow] = []
    order = 0
    for u in uses:
        if u.role != "music" or not u.audible:
            continue
        begin, end = u.timeline_from, u.timeline_to
        if span is not None:
            begin, end = max(begin, span[0]), min(end, span[1])
            if end <= begin:
                continue
        media: Media | None = media_by_sha.get(u.media_sha256)
        info = (media.extra.get("music_info") if media is not None else {})
        info = info or {}
        order += 1
        title = info.get("title", "")
        artist = info.get("artist", "")
        background = any(begin < s_end and end > s_start for s_start, s_end in speech)
        # Reports use whole seconds, and partial seconds round up (owner's
        # decision, 2026-10-17): the start is floored, the duration rounded up
        # and at least one second, and the out time is start plus duration, so
        # the three columns always agree.
        start = begin // rate
        length = max(1, -(-(end - begin) // rate))
        rows.append(ReportRow(
            order=order,
            title=title,
            artist=artist,
            composer=info.get("composer", ""),
            publisher=info.get("publisher", ""),
            isrc=info.get("isrc", ""),
            file_name=media.name if media is not None else "",
            in_time=_stamp(start),
            out_time=_stamp(start + length),
            duration=_stamp(length),
            background=background,
            missing_metadata=not (title and artist),
        ))
    return tuple(rows)


def _headers() -> tuple[str, ...]:
    return tuple(t(f"music_report.header.{key}") for key in _HEADER_KEYS)


def _usage(row: ReportRow) -> str:
    return t("music_report.background" if row.background else "music_report.featured")


def _metadata(row: ReportRow) -> str:
    return t("music_report.missing_metadata") if row.missing_metadata else ""


def _guard_formula(value: str) -> str:
    """Prefix cells starting with formula triggers (=, +, -, @) with a single quote.

    Spreadsheet applications like Excel interpret leading =, +, -, or @ as formula
    expressions, which can cause evaluation errors or formula injection.
    Quoting with a leading single quote ensures they are treated as plain text literals.
    """
    if value and value[0] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def render_csv(rows: tuple[ReportRow, ...]) -> str:
    """Semicolon-separated UTF-8 CSV, with Excel's UTF-8 signature.

    Cells starting with '=', '+', '-', or '@' are prefixed with a single quote
    to prevent spreadsheet formula injection in applications like Excel.
    """
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", quoting=csv.QUOTE_MINIMAL,
                        lineterminator="\n")
    writer.writerow(_headers())
    for r in rows:
        writer.writerow([
            str(r.order),
            _guard_formula(r.title),
            _guard_formula(r.artist),
            _guard_formula(r.composer),
            _guard_formula(r.publisher),
            _guard_formula(r.isrc),
            _guard_formula(r.file_name),
            r.in_time,
            r.out_time,
            r.duration,
            _usage(r),
            _metadata(r),
        ])
    return "\ufeff" + out.getvalue()


def render_html(rows: tuple[ReportRow, ...],
                *, title: str | None = None) -> str:
    """A printable HTML table of the report rows."""
    title = title or t("music_report.title")
    language = t("music_report.html_lang")

    def cell(text: str) -> str:
        return f"<td>{html.escape(str(text))}</td>"

    head = "".join(f"<th>{html.escape(h)}</th>" for h in _headers())
    body = "".join(
        "<tr>" + "".join(cell(v) for v in (
            r.order, r.title, r.artist, r.composer, r.publisher, r.isrc,
            r.file_name, r.in_time, r.out_time, r.duration,
            _usage(r), _metadata(r))) + "</tr>"
        for r in rows)
    return (
        f"<!DOCTYPE html><html lang=\"{html.escape(language)}\">"
        "<head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        "<style>table{border-collapse:collapse}th,td{border:1px solid #333;"
        "padding:4px 8px;text-align:left}</style></head>"
        f"<body><h1>{html.escape(title)}</h1>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody>"
        "</table></body></html>"
    )
