# ruff: noqa: E501  (one-off spike, not product code)
"""WP85 sweep: which Auto-Silence settings agree best with the owner's hand mutes?

    uv run python scripts/spikes/wp85_sweep.py INPUT.kuulas \
        [--minutes 3] [--margins 4,6,8,10,12,14] [--dominances 0,3,6,9,12,18,24] \
        [--min-opens 0.2,0.4,0.8] [--min-closeds 0.3,0.6,1,2] \
        [--befores 0.15,0.3,0.6] [--afters 0.4,0.8,1.5,3] \
        [--recall-floor 0.8] [--holdout] [--work DIR] [--allow-download]

INPUT is the episode as imported (audio, hand-made mutes in the first
minutes). The hand mutes are the ground truth, but only up to the last one
(the "hand window": it ends at the last hand mute of any speech track, and at
``--minutes`` at the latest, which is also how much of the episode is
analysed). Clips are unmuted for the measurement, as in wp85_compare.

Methods, all scored on the same ground truth, by time, per track and in total
(precision, recall, F1, seconds closed; "eaten" = seconds the owner KEPT open
that the method closed, the damage; "kept" = seconds the owner muted that the
method left open):

* current      Auto-Silence as it ships (margin 12 dB, dominance 6 dB, ...);
* margin, dominance, min_open, min_closed, open_before, open_after
               one knob swept at a time, the others at their defaults;
* grid         margin x dominance, every pair;
* compensated  the bleed-relative method (``bleed_relative``), calibrated on
               the hand mutes; its "presence" threshold takes each margin;
* combo        the ``COMBO_VALUES`` best values of every knob (least speech
               eaten at recall >= the floor), every combination.

``compensated`` learns from the very mutes it is scored on, so by default it is
scored IN-SAMPLE and flattered. ``--holdout`` calibrates it on the first half
of the hand window and scores every method on the second half only.

Prints the best total F1 (overall and per family), the Pareto-best settings by
(eaten, kept), the recommended one (recall >= ``--recall-floor`` with the least
speech eaten), per track the longest stretches the recommended setting and the
defaults close but the owner kept open (all of them in ``disagreements.csv``),
and diagnostics for the compensated method. The compensated rows are left out
of the Pareto set and the recommendation (experimental).

Read-only: the project's metadata is COPIED into ``--work`` and opened there;
the original is never opened by kuulas code, its audio is read in read mode.
Dropbox online-only placeholders stop the run unless ``--allow-download``.
Writes ``sweep.json`` and ``disagreements.csv`` into ``--work``.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np
from _readonly import ReadOnlyStore, all_unmuted, media_paths, mmss, muted_runs, open_copy
from wp85_compare import Level, intersect, merge, pct, subtract, track_span

from kuulas import analysis, bleed_relative
from kuulas.silence_options import SilenceOptions

RECALL_FLOOR = 0.9
#: The recall of the owner's mutes the recommendation must keep.
RECOMMEND_RECALL = 0.8
DEFAULT_MARGINS = (4, 6, 8, 10, 12, 14)
DEFAULT_DOMINANCES = (0, 3, 6, 9, 12, 18, 24)
#: The other knobs, swept one at a time: family -> (SilenceOptions field, values).
DEFAULT_KNOBS: dict[str, tuple[str, tuple[float, ...]]] = {
    "min_open": ("min_open_s", (0.2, 0.4, 0.8)),
    "min_closed": ("min_closed_s", (0.3, 0.6, 1.0, 2.0)),
    "open_before": ("open_before_s", (0.15, 0.3, 0.6)),
    "open_after": ("open_after_s", (0.4, 0.8, 1.5, 3.0)),
}
#: One-at-a-time family -> the SilenceOptions field it varies.
FAMILY_OPTION = {"margin": "margin_db", "dominance": "dominance_db",
                 **{f: opt for f, (opt, _v) in DEFAULT_KNOBS.items()}}
TOP_STRETCHES = 10
#: Values of each knob that go into the combination grid.
COMBO_VALUES = 2
PRINT_ORDER = ("current", "margin", "dominance", *DEFAULT_KNOBS, "grid", "compensated", "combo")


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
    """Precision, recall and F1 from frame counts (an empty side counts as perfect).
    ``eaten`` = closed but not muted by the owner (same as ``beyond``); ``kept`` =
    muted by the owner but left open."""
    precision = hit / method if method else 1.0
    recall = hit / truth if truth else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"closed": method, "truth": truth, "hit": hit, "beyond": method - hit,
            "eaten": method - hit, "kept": truth - hit,
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


def recommended(rows: list[dict], floor: float = RECOMMEND_RECALL) -> dict | None:
    """Among the rows (compensated left out) whose total recall reaches ``floor``, the
    one that eats the least speech; ties go to the better F1, then to less silence kept."""
    pool = [r for r in rows if r["family"] != "compensated" and r["total"]["recall"] >= floor]
    return min(pool, key=lambda r: (r["total"]["eaten"], -r["total"]["f1"], r["total"]["kept"]),
               default=None)


def pareto(rows: list[dict]) -> list[dict]:
    """The rows (compensated left out) no other row beats on BOTH speech eaten and
    silence kept; identical (eaten, kept) pairs appear once. Sorted by eaten."""
    pool = [r for r in rows if r["family"] != "compensated"]
    keyed = [(r["total"]["eaten"], r["total"]["kept"], i) for i, r in enumerate(pool)]
    out, seen = [], set()
    for eaten, kept, i in sorted(keyed):
        if (eaten, kept) in seen:
            continue
        if any(e <= eaten and k <= kept and (e, k) != (eaten, kept) for e, k, _ in keyed):
            continue
        seen.add((eaten, kept))
        out.append(pool[i])
    return out


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


def plan(margins, dominances, knobs=None) -> list[dict]:
    """The runs to make: ``{"family", "label", "options"}`` in print order. ``knobs``:
    family -> (option, values) for the timing knobs (none when omitted)."""
    base = SilenceOptions()
    rows = [{"family": "current", "label": "current", "options": base}]
    rows += [{"family": "margin", "label": f"margin {m:g}",
              "options": replace(base, margin_db=m)} for m in margins]
    rows += [{"family": "dominance", "label": f"dominance {d:g}",
              "options": replace(base, dominance_db=d)} for d in dominances]
    for family, (option, values) in (knobs or {}).items():
        rows += [{"family": family, "label": f"{option} {v:g}",
                  "options": replace(base, **{option: v})} for v in values]
    rows += [{"family": "grid", "label": f"margin {m:g} x dominance {d:g}",
              "options": replace(base, margin_db=m, dominance_db=d)}
             for m, d in itertools.product(margins, dominances)]
    rows += [{"family": "compensated", "label": f"compensated, presence {m:g}",
              "options": replace(base, margin_db=m, method="compensated")} for m in margins]
    return rows


def combo_label(options: SilenceOptions) -> str:
    return (f"m{options.margin_db:g} d{options.dominance_db:g} o{options.min_open_s:g} "
            f"c{options.min_closed_s:g} b{options.open_before_s:g} a{options.open_after_s:g}")


def plan_combos(rows: list[dict], floor: float = RECOMMEND_RECALL,
                per_knob: int = COMBO_VALUES) -> list[dict]:
    """The runs of the combination grid: for every swept knob its ``per_knob`` best values
    (recall >= ``floor`` first, then least speech eaten, then best F1), every combination.
    Settings equal to an earlier run are left out."""
    chosen: dict[str, list[float]] = {}
    for family, option in FAMILY_OPTION.items():
        fam = [r for r in rows if r["family"] == family]
        fam.sort(key=lambda r: (r["total"]["recall"] < floor, r["total"]["eaten"],
                                -r["total"]["f1"]))
        if fam:
            chosen[option] = [r["options"][option] for r in fam[:per_knob]]
    seen = {tuple(sorted(r["options"].items())) for r in rows}
    steps = []
    names = list(chosen)
    for values in itertools.product(*chosen.values()):
        options = replace(SilenceOptions(), **dict(zip(names, values, strict=True)))
        key = tuple(sorted(options.as_dict().items()))
        if key in seen:
            continue
        seen.add(key)
        steps.append({"family": "combo", "label": combo_label(options), "options": options})
    return steps


# -- disagreements: where the method ate what the owner kept ----------------------

def eaten_ranges(closed: dict, truth: dict, span: dict, lo: int, hi: int) -> dict:
    """Per track id the frame ranges inside the scored area that ``closed`` closes and the
    owner kept open."""
    out = {}
    for tid, truth_ranges in truth.items():
        area = clip_range(span[tid], lo, hi)
        method = intersect(merge(closed.get(tid, ())), area)
        out[tid] = subtract(method, intersect(merge(truth_ranges), area))
    return out


def stretch_rows(setting: str, eaten: dict, levels: dict, names: dict, rate: int) -> list[dict]:
    """One row per eaten stretch: where, how long, the track's own level and the loudest
    other track's level there (dBFS RMS, 20 ms hops)."""
    rows = []
    for tid, ranges in eaten.items():
        for a, b in ranges:
            own = levels[tid].dbfs(a, b)
            others = [(levels[o].dbfs(a, b), names[o]) for o in levels if o != tid]
            other_db, other_name = max(others, default=(float("-inf"), "-"))
            rows.append({"setting": setting, "track": names[tid], "start_s": a / rate,
                         "length_s": (b - a) / rate, "own_db": own,
                         "loudest_other": other_name, "other_db": other_db})
    return rows


def mmss1(sec: float) -> str:
    """``mm:ss.s`` (tenth of a second)."""
    tenths = round(sec * 10)
    return f"{tenths // 600:02d}:{tenths % 600 // 10:02d}.{tenths % 10}"


def fmt_db(x: float) -> str:
    return "   -inf" if x == float("-inf") else f"{x:6.1f}"


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = ["setting", "track", "start_s", "length_s", "start_mmss", "own_db",
              "loudest_other", "other_db"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({**r, "start_mmss": mmss1(r["start_s"]),
                        "start_s": f"{r['start_s']:.2f}", "length_s": f"{r['length_s']:.2f}",
                        "own_db": f"{r['own_db']:.1f}", "other_db": f"{r['other_db']:.1f}"})


def print_stretches(setting: str, rows: list[dict], out, top: int = TOP_STRETCHES) -> None:
    out(f"\n== eaten (closed, the owner kept open): {setting}")
    for name in dict.fromkeys(r["track"] for r in rows):
        mine = sorted((r for r in rows if r["track"] == name), key=lambda r: -r["length_s"])
        out(f"  {name}: {len(mine)} stretches, {sum(r['length_s'] for r in mine):.1f} s; longest {min(top, len(mine))}")
        out("    start      length   own dB  loudest other (dB)")
        for r in mine[:top]:
            out(f"    {mmss1(r['start_s'])}  {r['length_s']:7.1f} s {fmt_db(r['own_db'])}  "
                f"{r['loudest_other']} ({fmt_db(r['other_db']).strip()})")


# -- diagnostics of the compensated method ----------------------------------------

def pair_evidence(db: np.ndarray, valid: np.ndarray, muted: np.ndarray,
                  window: np.ndarray) -> np.ndarray:
    """``n[i, j]``: how many hops in ``window`` have mic ``i`` muted, ``j`` open and
    clearly speaking: the evidence ``bleed_relative.estimate_offsets`` has for the pair."""
    n = db.shape[0]
    floor = bleed_relative.floors(db, valid)
    out = np.zeros((n, n), dtype=int)
    for i, j in itertools.permutations(range(n), 2):
        hops = (window & valid[i] & valid[j] & muted[i] & ~muted[j]
                & (db[j] > floor[j] + bleed_relative.CALIBRATION_ACTIVE_DB))
        out[i, j] = int(hops.sum())
    return out


def compensated_diagnostics(db, valid, muted_cal, window_cal, truth_muted, scored,
                            presence_db: float) -> dict:
    """Why does the compensated method close (or not close) what it does? ``db``/``valid``
    are ``(mics, hops)``; ``muted_cal`` the hand mutes it learns from over ``window_cal``;
    ``truth_muted`` the owner's mutes everywhere; ``scored`` the bool hop window it is judged on.

    Returns the estimated ``offsets`` (and ``hops`` of evidence, ``fallback`` pairs that
    used the median), the same measured on the scored window with the full truth
    (``offsets_scored``, ``hops_scored``: do the calibration offsets transfer?), and per
    mic over the scored hops the shares of ``truth_open``, ``present`` (above its own
    floor + presence), ``speaking`` (the method), ``speaking_when_truth_muted`` and
    ``present_when_truth_muted`` (as a share of the owner's muted hops)."""
    offsets = bleed_relative.estimate_offsets(db, valid, muted_cal, window_cal)
    hops = pair_evidence(db, valid, muted_cal, window_cal)
    offsets_scored = bleed_relative.estimate_offsets(db, valid, truth_muted, scored)
    hops_scored = pair_evidence(db, valid, truth_muted, scored)
    n = db.shape[0]
    fallback = [(i, j) for i, j in itertools.permutations(range(n), 2)
                if hops[i, j] < bleed_relative.MIN_PAIR_HOPS]
    on = bleed_relative.speaking(db, valid, offsets, presence_db)
    floor = bleed_relative.floors(db, valid)
    present = valid & (db > floor[:, None] + presence_db)
    mics = []
    for i in range(n):
        area = scored & valid[i]
        muted_area = area & truth_muted[i]
        total = max(int(area.sum()), 1)
        mics.append({
            "hops": int(area.sum()),
            "truth_open": int((area & ~truth_muted[i]).sum()) / total,
            "present": int((area & present[i]).sum()) / total,
            "speaking": int((area & on[i]).sum()) / total,
            "speaking_when_truth_muted": (int((muted_area & on[i]).sum())
                                          / max(int(muted_area.sum()), 1)),
            "present_when_truth_muted": (int((muted_area & present[i]).sum())
                                         / max(int(muted_area.sum()), 1)),
            "speaking_when_truth_open": (int((area & ~truth_muted[i] & on[i]).sum())
                                         / max(int((area & ~truth_muted[i]).sum()), 1))})
    return {"offsets": offsets.tolist(), "hops": hops.tolist(),
            "fallback": [list(p) for p in fallback],
            "offsets_scored": offsets_scored.tolist(), "hops_scored": hops_scored.tolist(),
            "presence_db": presence_db, "mics": mics,
            "floor_db": floor.tolist()}


def print_diagnostics(d: dict, names: list[str], window: str, out) -> None:
    n = len(names)
    out(f"\n== compensated method, diagnostics (presence {d['presence_db']:g} dB; {window})")
    out("  bleed offset db_i - db_j in dB (i hears j) [evidence hops; * = fell back to the median]"
        "\n  and, in () the same measured on the SCORED window with the owner's full mutes:")
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            star = "*" if [i, j] in d["fallback"] else " "
            out(f"    {names[i][:14]:<14} hears {names[j][:14]:<14} {d['offsets'][i][j]:7.1f} dB "
                f"[{d['hops'][i][j]:5d}]{star} ({d['offsets_scored'][i][j]:7.1f} dB "
                f"[{d['hops_scored'][i][j]:5d}])")
    out(f"  pairs on the median fallback: {len(d['fallback'])} of {n * (n - 1)}")
    out("  per mic, over the scored hops (share of hops):")
    out(f"    {'':<14} owner-open  present  speaking | speaking if owner muted  present if owner muted  speaking if owner open")
    for name, m in zip(names, d["mics"], strict=True):
        out(f"    {name[:14]:<14} {pct(m['truth_open']):>10} {pct(m['present']):>8} {pct(m['speaking']):>9} |"
            f" {pct(m['speaking_when_truth_muted']):>24} {pct(m['present_when_truth_muted']):>23} {pct(m['speaking_when_truth_open']):>23}")
    out("  reading: 'speaking if owner muted' high = it leaves open what the owner muted"
        " (recall collapses); 'present if owner muted' high = every mic is above its floor"
        " all the time, so only the relative test can close it.")


def hop_mask(ranges, hop: int, hops: int) -> np.ndarray:
    """Bool per hop: wholly inside ``ranges`` (frames)."""
    out = np.zeros(hops, dtype=bool)
    for a, b in ranges:
        out[-(-a // hop):min(b // hop, hops)] = True
    return out


def line(label: str, total: dict, rate: int) -> str:
    return (f"  {label:<34} closes {total['closed'] / rate:7.1f} s  P {pct(total['precision']):>4} "
            f"R {pct(total['recall']):>4} F1 {pct(total['f1']):>4}  "
            f"eaten {total['eaten'] / rate:6.1f} s  kept {total['kept'] / rate:6.1f} s")


def run(inp_dir: Path, work: Path, minutes: float, margins, dominances, holdout: bool = False,
        allow_download: bool = False, out=print, knobs=None,
        recall_floor: float = RECOMMEND_RECALL) -> dict | None:
    knobs = DEFAULT_KNOBS if knobs is None else knobs
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
    window_text = (f"calibrated on {mmss(0)} to {mmss(lo / rate)}, scored from {mmss(lo / rate)} to {mmss(hi / rate)}"
                   if holdout else f"IN-SAMPLE: calibrated and scored on {mmss(0)} to {mmss(hi / rate)}")
    out(f"analysed: first {mmss(span_end / rate)}; hand window: {mmss(0)} to {mmss(hi / rate)}"
        + (f"; HOLDOUT: calibrated on the first half, scored from {mmss(lo / rate)}" if holdout
           else "; IN-SAMPLE: the compensated method is scored on the mutes it learned from"))

    pa = trimmed(all_unmuted(inp), span_end)
    pm = trimmed(inp, span_end)
    pm_cal = keep_mutes_before(pm, lo) if holdout else pm
    truth = {t.id: [r for r in muted_runs(t) if r[0] < hi] for t in speech}
    span = {t.id: track_span(t) for t in speech}
    names = {t.id: t.name for t in speech}
    hop = analysis.hop_frames(rate)

    store = ReadOnlyStore(paths, rate)
    # The levels do not depend on the options: measure each track once.
    real_levels, memo = analysis.track_levels, {}

    def cached(p, st, track):
        if track.id not in memo:
            memo[track.id] = real_levels(p, st, track)
        return memo[track.id]

    analysis.track_levels = cached
    rows: list[dict] = []
    closed_of: dict[str, dict] = {}
    diagnostics = None
    default_row: dict | None = None

    def execute(steps):
        for step in steps:
            options = step["options"]
            project = pm_cal if options.method == "compensated" else pa
            closed = analysis.silence_ranges(project, store, options)
            scored = score_method(closed, truth, span, lo, hi)
            row = {**step, "options": options.as_dict(), **scored}
            rows.append(row)
            closed_of[step["label"]] = closed

    try:
        execute(plan(margins, dominances, knobs))
        execute(plan_combos(rows, recall_floor))
        default_row = rows[0]
        levels = {}
        for t in speech:
            db, valid = cached(pa, store, t)
            levels[t.id] = Level(db, valid, hop)
        try:
            diagnostics = compensated_diag(pm_cal, pa, store, truth, lo, hi, hop, cached)
        except Exception as e:  # noqa: BLE001  (a diagnostic must not lose the sweep)
            out(f"compensated diagnostics failed: {e!r}")
    finally:
        analysis.track_levels = real_levels
        h.close()

    out("\n== per track: current method")
    for tid, tl in default_row["tracks"].items():
        out(line(names[tid][:34], tl, rate))
    out("\n== total, by time, against the hand mutes (precision / recall / F1; eaten = closed that the owner kept open; kept = muted by the owner but left open)")
    for family in PRINT_ORDER:
        for r in (r for r in rows if r["family"] == family):
            out(line(r["label"], r["total"], rate))
    out("\n== best F1 per family")
    summary = {}
    for name, pool in (("overall", rows),
                       *((f, [r for r in rows if r["family"] == f])
                         for f in PRINT_ORDER[1:] if any(r["family"] == f for r in rows))):
        best, safe = best_by_f1(pool), best_with_recall(pool)
        summary[name] = {"best_f1": best["label"] if best else None,
                         "best_f1_recall90": safe["label"] if safe else None}
        out(f"  {name:<12} best F1: {best['label'] if best else '-':<34}"
            f" best F1 with recall >= {RECALL_FLOOR:.0%}: {safe['label'] if safe else '(none reaches it)'}")
    front = pareto(rows)
    out("\n== Pareto-best by (speech eaten, silence kept), compensated left out")
    for r in front:
        out(line(r["label"], r["total"], rate))
    rec = recommended(rows, recall_floor)
    out(f"\n== recommended: recall of the owner's mutes >= {recall_floor:.0%}, least speech eaten")
    if rec:
        out(line(rec["label"], rec["total"], rate))
        out(f"  options {rec['options']}")
        out(f"  current: eaten {default_row['total']['eaten'] / rate:.1f} s, kept {default_row['total']['kept'] / rate:.1f} s")
        for tid, tl in rec["tracks"].items():
            out(line("  " + names[tid][:32], tl, rate))
    else:
        out("  (no setting reaches that recall)")
    top = best_by_f1(rows)
    out(f"\nbest F1: {top['label']}: F1 {pct(top['total']['f1'])} (current: "
        f"{pct(default_row['total']['f1'])}); options {top['options']}")
    if top["family"] == "compensated" and not holdout:
        out("  (compensated is in-sample here; confirm with --holdout before trusting it)")

    settings = [("current", default_row)] + ([("recommended " + rec["label"], rec)] if rec else [])
    stretches: list[dict] = []
    for setting, row in settings:
        eaten = eaten_ranges(closed_of[row["label"]], truth, span, lo, hi)
        mine = stretch_rows(setting, eaten, levels, names, rate)
        stretches += mine
        print_stretches(setting, mine, out)
    csv_path = work / "disagreements.csv"
    write_csv(csv_path, stretches)
    out(f"\nall eaten stretches: {csv_path}")

    if diagnostics:
        print_diagnostics(diagnostics, [names[t.id] for t in diagnostics.pop("tracks")],
                          window_text, out)
    result = {"rate": rate, "analysed_s": span_end / rate, "hand_window_s": hi / rate,
              "scored_from_s": lo / rate, "holdout": holdout, "names": names, "rows": rows,
              "recommendation": summary, "recommended": rec["label"] if rec else None,
              "pareto": [r["label"] for r in front], "compensated_diagnostics": diagnostics}
    path = work / "sweep.json"
    path.write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")
    out(f"full results: {path}")
    return result


def compensated_diag(pm_cal, pa, store, truth, lo, hi, hop, cached) -> dict | None:
    """The diagnostics of the compensated method on this episode (see
    ``compensated_diagnostics``), arranged as ``analysis._compensated_ranges`` does it.
    Adds ``tracks`` (the ordered track list) for the caller to print names from."""
    tracks = [t for t in analysis.speech_tracks(pm_cal) if not t.mute]
    if len(tracks) < 2:
        return None
    measured = [cached(pa, store, t) for t in tracks]
    db = np.stack([m[0] for m in measured]).astype(np.float64)
    valid = np.stack([m[1] for m in measured])
    hops = db.shape[1]
    muted_cal = np.stack([hop_mask(analysis.hand_mutes(t), hop, hops) for t in tracks])
    truth_muted = np.stack([hop_mask(truth[t.id], hop, hops) for t in tracks])
    end_h = -(-analysis.calibration_end(pm_cal) // hop)
    window_cal = np.arange(hops) < end_h
    scored = np.zeros(hops, dtype=bool)
    scored[-(-lo // hop):min(hi // hop, hops)] = True
    d = compensated_diagnostics(db, valid, muted_cal, window_cal, truth_muted, scored,
                                SilenceOptions().margin_db)
    d["calibration_window_hops"] = [0, int(end_h)]
    d["scored_window_hops"] = [int(np.flatnonzero(scored)[0]), int(np.flatnonzero(scored)[-1]) + 1]
    d["hop_s"] = hop / pa.rate
    d["tracks"] = tracks
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--minutes", type=float, default=3.0,
                    help="analyse (and score within) the first N minutes (default 3)")
    ap.add_argument("--margins", default=",".join(str(m) for m in DEFAULT_MARGINS))
    ap.add_argument("--dominances", default=",".join(str(m) for m in DEFAULT_DOMINANCES),
                    help="dominance_db values (shipped default 6)")
    ap.add_argument("--min-opens", default=",".join(map(str, DEFAULT_KNOBS["min_open"][1])))
    ap.add_argument("--min-closeds", default=",".join(map(str, DEFAULT_KNOBS["min_closed"][1])))
    ap.add_argument("--befores", default=",".join(map(str, DEFAULT_KNOBS["open_before"][1])))
    ap.add_argument("--afters", default=",".join(map(str, DEFAULT_KNOBS["open_after"][1])))
    ap.add_argument("--recall-floor", type=float, default=RECOMMEND_RECALL,
                    help="recall of the owner's mutes the recommendation must keep (default 0.8)")
    ap.add_argument("--holdout", action="store_true",
                    help="calibrate on the first half of the hand window, score the second")
    ap.add_argument("--work", type=Path)
    ap.add_argument("--allow-download", action="store_true",
                    help="read media that are cloud placeholders (makes Dropbox fetch them)")
    a = ap.parse_args()
    if not (a.input.resolve() / "project.sqlite").is_file():
        raise SystemExit(f"no project.sqlite in {a.input}")
    work = a.work or Path(tempfile.mkdtemp(prefix="wp85-sweep-"))
    given = {"min_open": a.min_opens, "min_closed": a.min_closeds,
             "open_before": a.befores, "open_after": a.afters}
    knobs = {f: (DEFAULT_KNOBS[f][0], tuple(parse_floats(text))) for f, text in given.items()}
    run(a.input.resolve(), work, a.minutes, parse_floats(a.margins), parse_floats(a.dominances),
        a.holdout, a.allow_download, knobs=knobs, recall_floor=a.recall_floor)


if __name__ == "__main__":
    main()
