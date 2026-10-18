"""Where to crossfade between two speakers.

``plan_fades`` plans one fade entry per boundary between consecutive turns of
different speakers. Errors are plain ``ValueError``; there is no user-facing
text. Inputs are never mutated.
"""

from __future__ import annotations


def plan_fades(turns: list[dict], long_gap: float = 0.5,
               fade: float = 0.12) -> list[dict]:
    """Plan fade entries at speaker change boundaries.

    Each entry is ``{"from", "to", "kind", "out_start", "out_end",
    "in_start", "in_end"}``. ``kind`` is ``"overlap"`` (talk-over, gap < 0,
    no fades), ``"crossfade"`` (0 <= gap <= long_gap, both sides fade over the
    midpoint window clamped into ``[prev.e, next.s]``), or ``"cut"``
    (gap > long_gap, out fades at the end of the previous turn, in fades at
    the start of the next).
    """
    if fade <= 0:
        msg = f"fade must be > 0, got {fade!r}"
        raise ValueError(msg)
    if long_gap < 0:
        msg = f"long_gap must be >= 0, got {long_gap!r}"
        raise ValueError(msg)

    fades: list[dict] = []
    prev_end: float | None = None
    prev_start: float | None = None
    prev_speaker: str | None = None

    for turn in turns:
        speaker = turn["speaker"]
        start = turn["s"]
        end = turn["e"]
        if end < start:
            msg = f"turn end must be >= start, got {turn!r}"
            raise ValueError(msg)
        if prev_start is not None and start < prev_start:
            msg = f"turns must be in time order, got {turn!r}"
            raise ValueError(msg)

        if prev_end is not None and prev_speaker is not None \
                and speaker != prev_speaker:
            gap = start - prev_end
            if gap < 0:
                fades.append({"from": prev_speaker, "to": speaker,
                              "kind": "overlap",
                              "out_start": None, "out_end": None,
                              "in_start": None, "in_end": None})
            elif gap <= long_gap:
                mid = (prev_end + start) / 2
                half = fade / 2
                out_start = max(prev_end, mid - half)
                out_end = min(start, mid + half)
                in_start = max(prev_end, mid - half)
                in_end = min(start, mid + half)
                fades.append({"from": prev_speaker, "to": speaker,
                              "kind": "crossfade",
                              "out_start": out_start, "out_end": out_end,
                              "in_start": in_start, "in_end": in_end})
            else:
                half = fade / 2
                fades.append({"from": prev_speaker, "to": speaker,
                              "kind": "cut",
                              "out_start": prev_end,
                              "out_end": prev_end + half,
                              "in_start": start - half,
                              "in_end": start})

        prev_start = start
        prev_end = end
        prev_speaker = speaker

    return fades
