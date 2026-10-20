"""Parse automixer flags file into structured flag dicts (T67)."""

import re
from typing import Any

# Line pattern:
# <start>-<end>  <name>  <block|loud> ...
# EN DASH (\u2013), EM DASH (\u2014), or hyphen (-)
_LINE_RE = re.compile(
    r"^(?P<start>(?:\d+:)?\d+:\d+(?:\.\d+)?)"
    r"[-\u2013\u2014]"
    r"(?P<end>(?:\d+:)?\d+:\d+(?:\.\d+)?)"
    r"\s{2,}"
    r"(?P<name>.+?)\s{2,}"
    r"(?P<kind>block|loud)\s+"
    r"(?P<rest>.*)$"
)

_BLOCK_REST_RE = re.compile(
    r"^([+-]?\d+(?:\.\d+)?)\s*dB.*?gain\s*([+-]?\d+(?:\.\d+)?)\s*dB",
    re.IGNORECASE,
)

_LOUD_REST_RE = re.compile(
    r"^([+-]?\d+(?:\.\d+)?)\s*dB",
    re.IGNORECASE,
)


def _parse_time(t_str: str) -> float:
    parts = t_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600.0 + int(parts[1]) * 60.0 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60.0 + float(parts[1])
    raise ValueError


def parse_flags(text: str) -> tuple[list[dict[str, Any]], list[tuple[int, str]]]:
    """Parse text lines from an automixer flags file.

    Returns:
        (flags, bad_lines) where flags is a list of dicts with:
            start_s: float
            end_s: float
            name: str
            kind: "block" | "loud"
            off_db: float
            gain_db: float | None
        and bad_lines is a list of (1-based line number, line text).
    """
    if not isinstance(text, str):
        return [], []

    flags: list[dict[str, Any]] = []
    bad_lines: list[tuple[int, str]] = []

    lines = text.splitlines()
    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped:
            continue

        match = _LINE_RE.match(line)
        if not match:
            bad_lines.append((idx, line))
            continue

        start_str = match.group("start")
        end_str = match.group("end")
        name = match.group("name").strip()
        kind = match.group("kind")
        rest = match.group("rest")

        try:
            start_s = _parse_time(start_str)
            end_s = _parse_time(end_str)
        except ValueError:
            bad_lines.append((idx, line))
            continue

        if kind == "block":
            rest_match = _BLOCK_REST_RE.search(rest)
            if not rest_match:
                bad_lines.append((idx, line))
                continue
            off_db = float(rest_match.group(1))
            gain_db: float | None = float(rest_match.group(2))
        elif kind == "loud":
            rest_match = _LOUD_REST_RE.search(rest)
            if not rest_match:
                bad_lines.append((idx, line))
                continue
            off_db = float(rest_match.group(1))
            gain_db = None
        else:
            bad_lines.append((idx, line))
            continue

        flags.append(
            {
                "start_s": start_s,
                "end_s": end_s,
                "name": name,
                "kind": kind,
                "off_db": off_db,
                "gain_db": gain_db,
            }
        )

    return flags, bad_lines
