"""Breath and pause classification from timed gaps.

Classify the stretches between words as ``silence``, ``breath`` or ``other``.
Pure Python, stdlib only: no imports from kuulas. Errors are plain ValueError;
there is no user-facing text.
"""

from __future__ import annotations


def classify_gaps(
    gaps: list[tuple[float, float, float]],
    silence_db: float,
    breath_db: float,
    min_breath: float,
    max_breath: float,
) -> list[dict]:
    """Classify each gap as ``silence``, ``breath`` or ``other``.

    ``gaps`` is a list of ``(start, end, rms_db)`` in any unit (frames or
    seconds). A gap is ``"silence"`` when ``rms_db <= silence_db``,
    ``"breath"`` when ``silence_db < rms_db <= breath_db`` and its length
    ``end - start`` is within ``[min_breath, max_breath]``, otherwise
    ``"other"``. Raises ``ValueError`` when ``breath_db <= silence_db``,
    ``min_breath > max_breath`` or any gap has ``end <= start``. Returns a list
    of ``{"start", "end", "kind"}`` in input order; the input is not mutated.
    """
    if breath_db <= silence_db:
        msg = f"breath_db ({breath_db}) must be > silence_db ({silence_db})"
        raise ValueError(msg)
    if min_breath > max_breath:
        msg = f"min_breath ({min_breath}) must be <= max_breath ({max_breath})"
        raise ValueError(msg)

    result: list[dict] = []
    for start, end, rms_db in gaps:
        if end <= start:
            msg = f"gap ({start}, {end}) has end <= start"
            raise ValueError(msg)
        length = end - start
        if rms_db <= silence_db:
            kind = "silence"
        elif rms_db <= breath_db and min_breath <= length <= max_breath:
            kind = "breath"
        else:
            kind = "other"
        result.append({"start": start, "end": end, "kind": kind})
    return result
