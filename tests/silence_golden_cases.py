"""The Auto-Silence golden cases: projects and options whose ``silence_ranges``
were recorded from the code BEFORE it was split into measure + decide (the
live preview). ``tests/golden/silence_ranges.json`` holds the answers;
``python tests/silence_golden_cases.py`` writes it again (only ever from a
version whose answers are trusted). Not a test module."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from gate_fixtures import RATE, conversation

from kuulas import analysis, ops
from kuulas.silence_options import SilenceOptions

GOLDEN = Path(__file__).parent / "golden" / "silence_ranges.json"

#: Option sets: the defaults, each control moved both ways, and the extremes.
OPTIONS: dict[str, SilenceOptions] = {
    "default": SilenceOptions(),
    "margin_low": SilenceOptions(margin_db=4.0),
    "margin_high": SilenceOptions(margin_db=18.0),
    "dominance_0": SilenceOptions(dominance_db=0.0),
    "dominance_20": SilenceOptions(dominance_db=20.0),
    "merge_wide": SilenceOptions(min_open_s=1.5, min_closed_s=0.8),
    "merge_none": SilenceOptions(min_open_s=0.0, min_closed_s=0.0),
    "padding": SilenceOptions(open_before_s=0.0, open_after_s=1.0),
    "padding_wide": SilenceOptions(open_before_s=0.5, open_after_s=2.5),
}

COMPENSATED: dict[str, SilenceOptions] = {
    "comp_default": SilenceOptions(method="compensated"),
    "comp_margin": SilenceOptions(method="compensated", margin_db=8.0),
    "comp_padding": SilenceOptions(method="compensated", open_after_s=1.0,
                                   min_closed_s=0.8),
}


def _hand_muted(p, store, seconds):
    for track_id, ranges in analysis.silence_ranges(p, store).items():
        cut = [(a, min(b, seconds * RATE)) for a, b in ranges if a < seconds * RATE]
        p = ops.mute_ranges(p, track_id, cut)
    return p


def projects():
    """name -> (project, store, option sets)."""
    out = {}
    p, store = conversation(seconds=90, seed=5, bleed=0.5)
    out["busy"] = (p, store, OPTIONS)
    p2, store2 = conversation(seconds=90, seed=11, bleed=0.2, turn=(0.5, 3.5))
    out["calm"] = (p2, store2, OPTIONS)
    # An old gate on one track (the measurement must not see it), a muted
    # track, and two tracks of one speaker.
    g = ops.set_gate(p, "T0", [(0, 20 * RATE), (40 * RATE, 50 * RATE)])
    out["gated"] = (g, store, OPTIONS)
    m = replace(p, tracks=tuple(replace(t, mute=True) if t.id == "T3" else t
                                for t in p.tracks))
    out["muted_track"] = (m, store, {"default": SilenceOptions()})
    same = replace(p, tracks=tuple(replace(t, speaker="Ann") if t.id in ("T1", "T2")
                                   else t for t in p.tracks))
    out["shared_speaker"] = (same, store, {"default": SilenceOptions(),
                                           "margin_low": OPTIONS["margin_low"]})
    # A clip moved off the start: hops before it are not valid.
    moved = ops.trim_clip(p, "c2", start=5 * RATE)
    out["late_clip"] = (moved, store, {"default": SilenceOptions()})
    # The compensated method: hand mutes in the first 40 s, with and without
    # a gate on top (its levels see the gate today).
    marked = _hand_muted(p, store, 40)
    out["hand_muted"] = (marked, store, {**COMPENSATED, "default": SilenceOptions()})
    marked_gated = ops.set_gate(marked, "T1", [(60 * RATE, 70 * RATE)])
    out["hand_muted_gated"] = (marked_gated, store, COMPENSATED)
    # A hand mute at the very end: the project (unmuted clips) is shorter than
    # what the compensated method measures over.
    tail = marked
    for clip_id in ("c1", "c2", "c3"):
        tail = ops.trim_clip(tail, clip_id, end=80 * RATE)
    tail = ops.mute_ranges(tail, "T0", [(80 * RATE, 90 * RATE)])
    out["hand_muted_tail"] = (tail, store, {**COMPENSATED, "default": SilenceOptions()})
    return out


def answers() -> dict:
    data = {}
    for name, (p, store, option_sets) in projects().items():
        for opt_name, opts in option_sets.items():
            ranges = analysis.silence_ranges(p, store, opts)
            data[f"{name}/{opt_name}"] = {k: [list(r) for r in v]
                                          for k, v in ranges.items()}
    return data


if __name__ == "__main__":
    GOLDEN.write_text(json.dumps(answers(), sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.write(f"wrote {GOLDEN}\n")
