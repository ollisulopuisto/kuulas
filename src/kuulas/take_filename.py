"""Self-describing take file names (T62).

Builds a filesystem-safe file name starting with local date and time,
followed by project, track, and take names.
"""

from __future__ import annotations

from datetime import datetime

from kuulas.safe_filename import safe_filename

MAX_LEN = 120


def _require_datetime(value: object, what: str) -> datetime:
    if not isinstance(value, datetime):
        msg = f"{what} must be a datetime, got {type(value).__name__}"
        raise ValueError(msg)  # noqa: TRY004 - the spec pins ValueError
    return value


def _require_string(value: object, what: str) -> str:
    if not isinstance(value, str):
        msg = f"{what} must be a string, got {type(value).__name__}"
        raise ValueError(msg)  # noqa: TRY004 - the spec pins ValueError
    return value


def _clean_part(text: str, max_len: int = MAX_LEN) -> str:
    """Sanitise text part; empty or whitespace-only is treated as empty."""
    if not text or not text.strip(" ."):
        return ""
    if max_len < 8:
        sanitised = safe_filename(text)
        return sanitised[:max_len].rstrip(" .") if max_len > 0 else ""
    return safe_filename(text, max_len=max_len)


def take_filename(when: datetime, project: str, track: str, take: str) -> str:
    """Return a safe, self-describing take file name.

    Format: ``"YYYY-MM-DD HH-MM-SS <project> - <track> - <take>"`` (at most 120 chars).
    Shortens the project part first if total length exceeds 120 characters;
    never the date or the take.
    """
    _require_datetime(when, "when")
    _require_string(project, "project")
    _require_string(track, "track")
    _require_string(take, "take")

    date_str = (
        f"{when.year:04d}-{when.month:02d}-{when.day:02d} "
        f"{when.hour:02d}-{when.minute:02d}-{when.second:02d}"
    )

    clean_proj = _clean_part(project)
    clean_track = _clean_part(track)
    clean_take = _clean_part(take)

    parts = [p for p in (clean_proj, clean_track, clean_take) if p]
    if not parts:
        return date_str

    full = f"{date_str} " + " - ".join(parts)
    if len(full) <= MAX_LEN:
        return full

    # Shorten project part first (never date or take)
    other_parts = [p for p in (clean_track, clean_take) if p]
    suffix = (" - " + " - ".join(other_parts)) if other_parts else ""
    fixed_len = len(date_str) + 1 + len(suffix)
    available_proj = MAX_LEN - fixed_len

    if clean_proj:
        if available_proj > 0:
            clean_proj = _clean_part(project, max_len=available_proj)
        else:
            clean_proj = ""

    parts = [p for p in (clean_proj, clean_track, clean_take) if p]
    if not parts:
        return date_str

    full = f"{date_str} " + " - ".join(parts)
    if len(full) <= MAX_LEN:
        return full

    # If still > MAX_LEN, shorten track (never date or take)
    if clean_track:
        take_suffix = f" - {clean_take}" if clean_take else ""
        proj_prefix = f"{clean_proj} - " if clean_proj else ""
        fixed_len = len(date_str) + 1 + len(proj_prefix) + len(take_suffix)
        available_track = MAX_LEN - fixed_len
        if available_track > 0:
            clean_track = _clean_part(track, max_len=available_track)
        else:
            clean_track = ""

    parts = [p for p in (clean_proj, clean_track, clean_take) if p]
    if not parts:
        return date_str

    return f"{date_str} " + " - ".join(parts)
