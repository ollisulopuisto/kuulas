"""Recordings list model for take management.

Pure Python logic for formatting, sorting, and reporting take usage status.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def take_rows(
    takes: list[dict[str, Any]] | None,
    used_files: set[str],
) -> list[dict[str, Any]]:
    """Format and sort takes newest first, with tie-breaking by case-insensitive name."""
    if not takes:
        return []

    rows: list[dict[str, Any]] = []
    for t in takes:
        file = str(t.get("file", ""))
        created_val = t.get("created")
        created = float(created_val) if created_val is not None else 0.0

        duration_val = t.get("duration_s")
        duration_s = float(duration_val) if duration_val is not None else 0.0

        name_val = t.get("name")
        name = str(name_val) if name_val is not None else Path(file).stem

        used = file in used_files

        rows.append({
            "name": name,
            "file": file,
            "created": created,
            "duration_s": duration_s,
            "used": used,
        })

    rows.sort(key=lambda r: (-r["created"], r["name"].lower()))
    return rows


def unused_count(rows: list[dict[str, Any]]) -> int:
    """Return how many rows have used == False."""
    return sum(1 for r in rows if not r.get("used", False))
