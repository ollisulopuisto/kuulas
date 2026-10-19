"""Muted and gated stretches of a track on its stem's own clock (WP85).

The stems export lists them in ``tracks.json`` so an external tool can see
the hand-made mutes (``muted_frames``) apart from the machine-made
Auto-Silence gate (``gate_frames``). Frame 0 is the stem's first sample, the
timeline frame ``first``; ranges are ``[start, end)``, sorted, merged and
clipped to ``[0, frames)``.
"""

from collections.abc import Iterable

from kuulas.model import Track


def on_stem_clock(ranges: Iterable[tuple[int, int]], first: int,
                  frames: int) -> list[list[int]]:
    """Timeline ranges as merged stem-clock ranges, clipped to the export.
    Overlapping and touching ranges become one; empty ones are dropped."""
    out: list[list[int]] = []
    clipped = sorted((max(0, int(a) - first), min(frames, int(b) - first))
                     for a, b in ranges)
    for start, end in clipped:
        if end <= start:
            continue
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out


def muted_ranges(track: Track, first: int, frames: int) -> list[list[int]]:
    """The track's hand-made clip mutes. The gate is not included."""
    muted = ((c.start, c.end) for c in track.clips if c.muted)
    return on_stem_clock(muted, first, frames)


def gate_ranges(track: Track, first: int, frames: int) -> list[list[int]]:
    """The track's Auto-Silence gate ranges. Hand-made mutes are not included."""
    return on_stem_clock(track.gate, first, frames)
