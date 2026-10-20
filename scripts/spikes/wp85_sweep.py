# ruff: noqa: E501  (one-off spike, not product code)
"""WP85 sweep: which Auto-Silence settings agree best with the owner's hand mutes?

    uv run python scripts/spikes/wp85_sweep.py INPUT.kuulas \
        [--minutes 3] [--margins 4,6,8,10,12,14] [--dominances 6] \
        [--holdout] [--work DIR] [--allow-download]

INPUT is the episode as imported (audio, hand-made mutes in the first
minutes). The hand mutes are the ground truth, but only up to the last one
(the "hand window": it ends at the last hand mute of any speech track, and at
``--minutes`` at the latest, which is also how much of the episode is
analysed). Clips are unmuted for the measurement, as in wp85_compare.

Methods, all scored on the same ground truth, by time, per track and in total
(precision, recall, F1, seconds closed, "beyond" = seconds closed that the
owner did not mute):

* current      Auto-Silence as it ships (margin 12 dB, dominance 6 dB);
* margin       ``margin_db`` swept (``--margins``), dominance at its default;
* dominance    ``dominance_db`` swept (``--dominances``), margin at its default;
* grid         margin x dominance, every pair;
* compensated  the bleed-relative method (``bleed_relative``), calibrated on
               the hand mutes; its "presence" threshold takes each margin.

``compensated`` learns from the very mutes it is scored on, so by default it is
scored IN-SAMPLE and flattered. ``--holdout`` calibrates it on the first half
of the hand window and scores every method on the second half only.

Prints the best total F1 and the best total F1 with recall >= 0.9 (overall and
per family). Read-only: the project's metadata is COPIED into ``--work`` and
opened there; the original is never opened by kuulas code, its audio is read in
read mode. Dropbox online-only placeholders stop the run unless
``--allow-download``. Writes ``sweep.json`` into ``--work``.
"""

from __future__ import annotations

import argparse
import itertools
import json
import tempfile
from dataclasses import replace
from pathlib import Path

from _readonly import ReadOnlyStore, all_unmuted, media_paths, mmss, muted_runs, open_copy
from wp85_compare import intersect, merge, pct, track_span

from kuulas import analysis
from kuulas.silence_options import SilenceOptions

RECALL_FLOOR = 0.9
DEFAULT_MARGINS = (4, 6, 8, 10, 12, 14)


def parse_floats(text: str) -> list[float]:
    """``"4,6,8"`` -> ``[4.0, 6.0, 8.0]``; blanks ignored, order kept, no repeats."""
    out: list[float] = []
    for part in text.split(","):
        if part.strip() and (value := float(part)) not in out:
            out.append(value)
    if not out:
        raise ValueError("no numbers")
    return out


def total_ranges(r) -> int:
    return sum(b - a for a, b in r)


def clip_range(r, lo: int, hi: int):
    """``r`` restricted to the frames [lo, hi)."""
    return intersect(merge(r), [(lo, hi)]) if hi > lo else []


def tally(method: int, truth: int, hit: int) -> dict:
    """Precision, recall and F1 from frame counts (an empty side counts as perfect)."""
    precision = hit / method if method else 1.0
    recall = hit / truth if truth else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"closed": method, "truth": truth, "hit": hit, "beyond": method - hit,
            "precision": precision, "recall": recall, "f1": f1}


def score_method(closed: dict, truth: dict, span: dict, lo: int, hi: int) -> dict:
    """``{"tracks": {id: tally}, "total": tally}`` of ``closed`` (track id -> ranges)
    against ``truth`` inside each track's span and the frames [lo, hi)."""
    tracks, sums = {}, [0, 0, 0]
    for tid, truth_ranges in truth.items():
        area = clip_range(span[tid], lo, hi)
        method = intersect(merge(closed.get(tid, ())), area)
        wanted = intersect(merge(truth_ranges), area)
        hit = total_ranges(intersect(method, wanted))
        tracks[tid] = tally(total_ranges(method), total_ranges(wanted), hit)
        sums = [sums[0] + total_ranges(method), sums[1] + total_ranges(wanted), sums[2] + hit]
    return {"tracks": tracks, "total": tally(*sums)}


def best_by_f1(rows: list[dict]) -> dict | None:
    return max(rows, key=lambda r: r["total"]["f1"], default=None)


def best_with_recall(rows: list[dict], floor: float = RECALL_FLOOR) -> dict | None:
    """The row with the best total F1 among those whose total recall reaches ``floor``."""
    return best_by_f1([r for r in rows if r["total"]["recall"] >= floor])


def trimmed(p, end: int):
    """``p`` with every clip cut to the frames before ``end`` (clips starting later dropped)."""
    def cut(track):
        clips = tuple(replace(c, length=min(c.end, end) - c.start)
                      for c in track.clips if c.start < end)
        return replace(track, clips=clips, gate=())
    return replace(p, tracks=tuple(cut(t) for t in p.tracks))


def keep_mutes_before(p, frame: int):
    """``p`` with the hand mutes that start at or after ``frame`` undone."""
    return replace(p, tracks=tuple(
        replace(t, clips=tuple(replace(c, muted=c.muted and c.start < frame) for c in t.clips))
        for t in p.tracks))


def plan(margins, dominances) -> list[dict]:
    """The runs to make: ``{"family", "label", "options"}`` in print order."""
    base = SilenceOptions()
    rows = [{"family": "current", "label": "current", "options": base}]
    rows += [{"family": "margin", "label": f"margin {m:g}",
              "options": replace(base, margin_db=m)} for m in margins]
    rows += [{"family": "dominance", "label": f"dominance {d:g}",
              "options": replace(base, dominance_db=d)} for d in dominances]
    rows += [{"family": "grid", "label": f"margin {m:g} x dominance {d:g}",
              "options": replace(base, margin_db=m, dominance_db=d)}
             for m, d in itertools.product(margins, dominances)]
    rows += [{"family": "compensated", "label": f"compensated, presence {m:g}",
              "options": replace(base, margin_db=m, method="compensated")} for m in margins]
    return rows


def line(label: str, total: dict, rate: int) -> str:
    return (f"  {label:<34} closes {total['closed'] / rate:7.1f} s  P {pct(total['precision']):>4} "
            f"R {pct(total['recall']):>4} F1 {pct(total['f1']):>4}  beyond {total['beyond'] / rate:6.1f} s")


def run(inp_dir: Path, work: Path, minutes: float, margins, dominances, holdout: bool = False,
        allow_download: bool = False, out=print) -> dict | None:
    work.mkdir(parents=True, exist_ok=True)
    h = open_copy(inp_dir, work / "input")
    out(f"metadata copied to {work} (original folder not opened)")
    inp = h.state
    rate = inp.rate
    paths, problems = media_paths(h, inp_dir, allow_download)
    for p_ in problems:
        out("MEDIA", p_)
    speech = analysis.speech_tracks(inp)
    if not speech:
        out("STOP: no speech tracks")
        return None
    if any(c.media not in paths for t in speech for c in t.clips):
        out("STOP: audio of a speech track is missing or online-only; nothing was downloaded "
            "(use --allow-download to read placeholders)")
        return None
    span_end = min(inp.length, round(minutes * 60 * rate)) if minutes else inp.length
    hand_end = max((b for t in speech for _a, b in muted_runs(t)), default=0)
    hi = min(hand_end, span_end)
    if hi <= 0:
        out("STOP: no hand-made mutes in the analysed part; nothing to learn from or score against")
        return None
    lo = hi // 2 if holdout else 0
    out(f"analysed: first {mmss(span_end / rate)}; hand window: {mmss(0)} to {mmss(hi / rate)}"
        + (f"; HOLDOUT: calibrated on the first half, scored from {mmss(lo / rate)}" if holdout
           else "; IN-SAMPLE: the compensated method is scored on the mutes it learned from"))

    pa = trimmed(all_unmuted(inp), span_end)
    pm = trimmed(inp, span_end)
    pm_cal = keep_mutes_before(pm, lo) if holdout else pm
    truth = {t.id: [r for r in muted_runs(t) if r[0] < hi] for t in speech}
    span = {t.id: track_span(t) for t in speech}
    names = {t.id: t.name for t in speech}

    store = ReadOnlyStore(paths, rate)
    # The levels do not depend on the options: measure each track once.
    real_levels, memo = analysis.track_levels, {}

    def cached(p, st, track):
        if track.id not in memo:
            memo[track.id] = real_levels(p, st, track)
        return memo[track.id]

    analysis.track_levels = cached
    rows = []
    try:
        for step in plan(margins, dominances):
            options = step["options"]
            project = pm_cal if options.method == "compensated" else pa
            closed = analysis.silence_ranges(project, store, options)
            scored = score_method(closed, truth, span, lo, hi)
            rows.append({**step, "options": options.as_dict(), **scored})
    finally:
        analysis.track_levels = real_levels
        h.close()

    out("\n== per track: current method")
    cur = rows[0]
    for tid, tl in cur["tracks"].items():
        out(line(names[tid][:34], tl, rate))
    out("\n== total, by time, against the hand mutes (precision / recall / F1)")
    for family in ("current", "margin", "dominance", "grid", "compensated"):
        for r in (r for r in rows if r["family"] == family):
            out(line(r["label"], r["total"], rate))
    out("\n== recommendation")
    summary = {}
    for name, pool in (("overall", rows),
                       *((f, [r for r in rows if r["family"] == f])
                         for f in ("margin", "dominance", "grid", "compensated"))):
        best, safe = best_by_f1(pool), best_with_recall(pool)
        summary[name] = {"best_f1": best["label"] if best else None,
                         "best_f1_recall90": safe["label"] if safe else None}
        out(f"  {name:<12} best F1: {best['label'] if best else '-':<34}"
            f" best F1 with recall >= {RECALL_FLOOR:.0%}: {safe['label'] if safe else '(none reaches it)'}")
    top = best_by_f1(rows)
    out(f"\nbest: {top['label']}: F1 {pct(top['total']['f1'])} (current: "
        f"{pct(cur['total']['f1'])}); options {top['options']}")
    if top["family"] == "compensated" and not holdout:
        out("  (compensated is in-sample here; confirm with --holdout before trusting it)")
    if top["tracks"]:
        out("per track for the best:")
        for tid, tl in top["tracks"].items():
            out(line(names[tid][:34], tl, rate))
    result = {"rate": rate, "analysed_s": span_end / rate, "hand_window_s": hi / rate,
              "scored_from_s": lo / rate, "holdout": holdout, "rows": rows,
              "recommendation": summary}
    path = work / "sweep.json"
    path.write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")
    out(f"full results: {path}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--minutes", type=float, default=3.0,
                    help="analyse (and score within) the first N minutes (default 3)")
    ap.add_argument("--margins", default=",".join(str(m) for m in DEFAULT_MARGINS))
    ap.add_argument("--dominances", default="6", help="dominance_db values (default: the shipped 6)")
    ap.add_argument("--holdout", action="store_true",
                    help="calibrate on the first half of the hand window, score the second")
    ap.add_argument("--work", type=Path)
    ap.add_argument("--allow-download", action="store_true",
                    help="read media that are cloud placeholders (makes Dropbox fetch them)")
    a = ap.parse_args()
    if not (a.input.resolve() / "project.sqlite").is_file():
        raise SystemExit(f"no project.sqlite in {a.input}")
    work = a.work or Path(tempfile.mkdtemp(prefix="wp85-sweep-"))
    run(a.input.resolve(), work, a.minutes, parse_floats(a.margins), parse_floats(a.dominances),
        a.holdout, a.allow_download)


if __name__ == "__main__":
    main()
