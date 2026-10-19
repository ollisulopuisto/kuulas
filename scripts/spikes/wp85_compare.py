# ruff: noqa: E501  (one-off spike, not product code)
"""WP85 spike: how close is kuulas Auto-Silence to colab-transcribe's mutes?

    uv run python scripts/spikes/wp85_compare.py INPUT.kuulas PROCESSED.kuulas \
        [--minutes N | --all] [--work DIR] [--allow-download]

INPUT is the episode as imported from the Hindenburg session (audio,
transcript, hand-made mutes in the first minutes); PROCESSED is the same
episode as processed by colab-transcribe (machine-made mutes, sometimes too
many). Neither machine method is ground truth; the hand-made mutes of INPUT
are, but only up to the last one (the "hand window"). So:

1. each method (colab-transcribe, kuulas Auto-Silence) is scored against the
   hand mutes inside the hand window, per track: precision, recall, F1 by
   time, and "beyond" = seconds it closes that the owner did not mute;
2. the two methods are compared over the whole episode (or --minutes N).

Per track (matched by name):

* colab-transcribe = the PROCESSED track's muted clip runs (and gate, if any), seconds;
* kuulas = ``analysis.silence_ranges`` on INPUT with every clip unmuted and
  ungated (the hand mutes do not bias it);
* seconds muted by each, both, only colab-transcribe, only kuulas, Jaccard;
* the longest disagreement runs in each direction with the track's own
  level (dBFS RMS, kuulas's 20 ms measure) and the loudest OTHER track's
  level there (bleed or real speech?).

Read-only: both projects' metadata is COPIED into ``--work`` (default a fresh
temp dir) and opened there; the originals are never opened by kuulas code.
INPUT audio is read in read mode. Dropbox online-only placeholders stop the
run unless ``--allow-download``. The PROCESSED project's audio is not used.
Comparison is limited to where INPUT's clips of the track lie. Writes
``disagreements.csv`` and ``compare.json`` into ``--work``.
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path

import numpy as np
from _readonly import (
    ReadOnlyStore,
    all_unmuted,
    media_paths,
    mmss,
    muted_runs,
    open_copy,
)

from kuulas import analysis

TOP = 15
Ranges = list[tuple[int, int]]


# -- interval arithmetic on sorted, merged (start, end) frame pairs -----------

def merge(ranges) -> Ranges:
    out: list[list[int]] = []
    for a, b in sorted((int(a), int(b)) for a, b in ranges if b > a):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def intersect(r1: Ranges, r2: Ranges) -> Ranges:
    out, i, j = [], 0, 0
    while i < len(r1) and j < len(r2):
        a, b = max(r1[i][0], r2[j][0]), min(r1[i][1], r2[j][1])
        if b > a:
            out.append((a, b))
        if r1[i][1] < r2[j][1]:
            i += 1
        else:
            j += 1
    return out


def subtract(r1: Ranges, r2: Ranges) -> Ranges:
    out = []
    for a, b in r1:
        cur = a
        for c, d in r2:
            if d <= cur:
                continue
            if c >= b:
                break
            if c > cur:
                out.append((cur, c))
            cur = max(cur, d)
        if cur < b:
            out.append((cur, b))
    return out


def total(r: Ranges) -> int:
    return sum(b - a for a, b in r)


def clip_window(r: Ranges, hi: int) -> Ranges:
    return [(a, min(b, hi)) for a, b in r if a < hi]


def track_span(track) -> Ranges:
    return merge((c.start, c.end) for c in track.clips)


# -- levels ---------------------------------------------------------------------

class Level:
    """dBFS RMS over timeline ranges, from per-hop dB (power) with prefix sums."""

    def __init__(self, db: np.ndarray, valid: np.ndarray, hop: int):
        power = np.where(valid, 10.0 ** (db.astype(np.float64) / 10.0), 0.0)
        self.cum = np.concatenate(([0.0], np.cumsum(power)))
        self.cnt = np.concatenate(([0], np.cumsum(valid.astype(np.int64))))
        self.hop = hop

    def dbfs(self, a: int, b: int) -> float:
        lo = min(a // self.hop, self.cum.size - 1)
        hi = min(max(lo + 1, -(-b // self.hop)), self.cum.size - 1)
        n = self.cnt[hi] - self.cnt[lo]
        if n <= 0:
            return float("-inf")
        mean = (self.cum[hi] - self.cum[lo]) / n
        return float(10.0 * np.log10(mean)) if mean > 0 else float("-inf")


def fmt_db(x: float) -> str:
    return "  -inf" if x == float("-inf") else f"{x:6.1f}"


# -- comparison ---------------------------------------------------------------

def compare_track(ref: Ranges, auto: Ranges, span: Ranges, window: int) -> dict:
    """Agreement of two closed-range sets inside ``span`` and ``[0, window)``."""
    area = clip_window(span, window)
    ref = intersect(merge(clip_window(ref, window)), area)
    auto = intersect(merge(clip_window(auto, window)), area)
    both = intersect(ref, auto)
    return {"ref": ref, "auto": auto, "both": both,
            "only_ct": subtract(ref, auto), "only_k": subtract(auto, ref),
            "union": total(ref) + total(auto) - total(both), "area": total(area)}


def score(method: Ranges, truth: Ranges) -> dict:
    """Precision/recall/F1 by time of ``method`` against ``truth``, and the
    seconds-in-frames the method closes beyond the truth."""
    hit = total(intersect(method, truth))
    m, t = total(method), total(truth)
    prec = hit / m if m else 1.0
    rec = hit / t if t else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"method": m, "truth": t, "hit": hit, "precision": prec, "recall": rec,
            "f1": f1, "beyond": m - hit}


def pct(x: float) -> str:
    return f"{x:.0%}"


def match_tracks(inp, proc):
    """``[(input track, processed track)]`` by name, plus the unmatched names."""
    def key(t):
        return t.name.strip().casefold()

    by_name: dict[str, list] = {}
    for t in proc.tracks:
        if t.kind == "speech" and t.clips:
            by_name.setdefault(key(t), []).append(t)
    pairs, left = [], []
    for t in analysis.speech_tracks(inp):
        cands = by_name.get(key(t))
        if cands:
            pairs.append((t, cands.pop(0)))
        else:
            left.append(f"input only: {t.name}")
    for cands in by_name.values():
        left += [f"processed only: {t.name}" for t in cands]
    return pairs, left


def run(inp_dir: Path, proc_dir: Path, work: Path, minutes: float | None,
        allow_download: bool = False, out=print) -> dict | None:
    work.mkdir(parents=True, exist_ok=True)
    hi = open_copy(inp_dir, work / "input")
    hp = open_copy(proc_dir, work / "processed")
    out(f"metadata copied to {work} (original folders not opened)")
    inp, proc = hi.state, hp.state
    rate = inp.rate
    if proc.rate != rate:
        raise SystemExit(f"rates differ: input {rate}, processed {proc.rate}")
    window = inp.length if minutes is None else round(minutes * 60 * rate)
    pairs, left = match_tracks(inp, proc)
    for line in left:
        out("UNMATCHED", line)
    if not pairs:
        out("STOP: no track names match")
        return None
    if abs(inp.length - proc.length) > rate:
        out(f"WARNING: timelines differ: input {inp.length / rate:.1f} s, "
            f"processed {proc.length / rate:.1f} s; tracks may not line up")

    paths, problems = media_paths(hi, inp_dir, allow_download)
    for line in problems:
        out("MEDIA", line)
    if any(c.media not in paths for t, _p in pairs for c in t.clips):
        out("STOP: audio of a matched input track is missing or online-only; "
            "nothing was downloaded (use --allow-download to read placeholders)")
        return None

    store = ReadOnlyStore(paths, rate)
    pa = all_unmuted(inp)
    closed = analysis.silence_ranges(pa, store)
    hop = analysis.hop_frames(rate)
    levels = {}
    for t, _p in pairs:
        db, valid = analysis.track_levels(pa, store, pa.track(t.id))
        levels[t.id] = Level(db, valid, hop)

    hand_end = max((b for t, _p in pairs for _a, b in muted_runs(t)), default=0)
    hand_sums = {m: dict.fromkeys(("method", "truth", "hit", "beyond"), 0)
                 for m in ("colab-transcribe", "kuulas")}
    result: dict = {"hand_window_s": hand_end / rate, "rate": rate, "window_s": window / rate, "unmatched": left, "tracks": {}}
    rows: list[dict] = []
    sums = dict.fromkeys(("ref", "auto", "both", "only_ct", "only_k", "union"), 0)
    for t, pt in pairs:
        ref = merge([*muted_runs(pt), *pt.gate])
        auto = merge(closed.get(t.id, ()))
        c = compare_track(ref, auto, track_span(t), window)
        horizon = max((b for _a, b in muted_runs(t)), default=0)
        hand = intersect(merge(muted_runs(t)), clip_window(track_span(t), window))
        info = {k: total(c[k]) / rate for k in ("ref", "auto", "both", "only_ct", "only_k")}
        info["jaccard"] = (total(c["both"]) / c["union"]) if c["union"] else 1.0
        info["hand_s"] = total(hand) / rate
        info["hand_horizon_s"] = horizon / rate
        info["hand_in_ct_s"] = total(intersect(hand, c["ref"])) / rate
        info["hand_in_kuulas_s"] = total(intersect(hand, c["auto"])) / rate
        # ground truth: hand mutes inside the hand window (to the last hand mute of
        # any track), scored against both methods over the same window
        hw = compare_track(ref, auto, track_span(t), hand_end)
        truth = intersect(merge(muted_runs(t)), clip_window(track_span(t), hand_end))
        scores = {"colab-transcribe": score(hw["ref"], truth), "kuulas": score(hw["auto"], truth)}
        info["vs_hand"] = scores
        for m, sc in scores.items():
            for k in hand_sums[m]:
                hand_sums[m][k] += sc[k]
        for k in sums:
            sums[k] += c[k] if k == "union" else total(c[k])
        others = [x for x, _p in pairs if x.id != t.id]
        track_runs = {}
        for direction, key in (("only-colab", "only_ct"),
                               ("only-kuulas", "only_k")):
            ranked = sorted(c[key], key=lambda r: r[0] - r[1])
            lst = []
            for a, b in ranked:
                own = levels[t.id].dbfs(a, b)
                loud = max(((levels[o.id].dbfs(a, b), o.name) for o in others),
                           default=(float("-inf"), ""))
                lst.append({"track": t.name, "direction": direction,
                            "start_s": round(a / rate, 3), "end_s": round(b / rate, 3),
                            "length_s": round((b - a) / rate, 3),
                            "track_dbfs": round(own, 1), "loudest_other_dbfs": round(loud[0], 1),
                            "loudest_other": loud[1]})
            rows += lst
            track_runs[direction] = lst[:TOP]
        n_runs = {"only-colab": len(c["only_ct"]), "only-kuulas": len(c["only_k"])}
        result["tracks"][t.name] = {**info, "runs": track_runs, "n_runs": n_runs}

        out(f"\n== [{t.name}] muted: colab-transcribe {info['ref']:.1f} s, kuulas "
            f"{info['auto']:.1f} s; both {info['both']:.1f}, only-ct {info['only_ct']:.1f}, "
            f"only-kuulas {info['only_k']:.1f}; Jaccard {pct(info['jaccard'])}")
        out(f"   input hand mutes: {info['hand_s']:.1f} s (last ends {mmss(horizon / rate)}); "
            f"of those colab-transcribe has {info['hand_in_ct_s']:.1f} s, kuulas "
            f"{info['hand_in_kuulas_s']:.1f} s")
        for m, sc in scores.items():
            out(f"   vs hand mutes (to {mmss(hand_end / rate)}): {m:<16} closes "
                f"{sc['method'] / rate:6.1f} s of which {sc['hit'] / rate:6.1f} s hand-muted "
                f"(truth {sc['truth'] / rate:.1f} s); precision {pct(sc['precision'])} recall "
                f"{pct(sc['recall'])} F1 {pct(sc['f1'])}; beyond {sc['beyond'] / rate:.1f} s")
        for direction, lst in track_runs.items():
            out(f"   longest {direction} (top {TOP} of {n_runs[direction]}):")
            for r in lst:
                out(f"     {mmss(r['start_s'])} +{r['length_s']:6.2f} s  own {fmt_db(r['track_dbfs'])} dB"
                    f"  loudest other {fmt_db(r['loudest_other_dbfs'])} dB ({r['loudest_other']})")

    j = sums["both"] / sums["union"] if sums["union"] else 1.0
    result["hand_total"] = {}
    for m, h in hand_sums.items():
        pr = h["hit"] / h["method"] if h["method"] else 1.0
        rc = h["hit"] / h["truth"] if h["truth"] else 1.0
        result["hand_total"][m] = {
            "closed_s": h["method"] / rate, "truth_s": h["truth"] / rate,
            "hit_s": h["hit"] / rate, "beyond_s": h["beyond"] / rate,
            "precision": pr, "recall": rc, "f1": 2 * pr * rc / (pr + rc) if pr + rc else 0.0}
    result["total"] = {**{k: v / rate for k, v in sums.items()}, "jaccard": j}
    csv_path, json_path = work / "disagreements.csv", work / "compare.json"
    fields = ["track", "direction", "start_s", "end_s", "length_s", "track_dbfs",
              "loudest_other_dbfs", "loudest_other"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    json_path.write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")
    hi.close()
    hp.close()

    out("\n== SUMMARY (neither machine method is ground truth)")
    out(f"vs hand mutes, first {mmss(hand_end / rate)} (the ground truth), by time:")
    for name, i in result["tracks"].items():
        a, b = i["vs_hand"]["colab-transcribe"], i["vs_hand"]["kuulas"]
        out(f"  {name[:16]:<16} truth {a['truth'] / rate:5.1f} s | colab P {pct(a['precision'])} R "
            f"{pct(a['recall'])} beyond {a['beyond'] / rate:5.1f} s | kuulas P {pct(b['precision'])} "
            f"R {pct(b['recall'])} beyond {b['beyond'] / rate:5.1f} s")
    for m, h in result["hand_total"].items():
        out(f"  TOTAL {m:<16} P {pct(h['precision'])} R {pct(h['recall'])} F1 {pct(h['f1'])} "
            f"beyond {h['beyond_s']:.1f} s")
    out("colab-transcribe vs kuulas, whole window:")
    out(f"window {mmss(window / rate)} of {mmss(inp.length / rate)}; tracks compared "
        f"{len(pairs)}, unmatched {len(left)}")
    out(f"{'track':<18} {'ct s':>8} {'kuulas s':>9} {'both':>8} {'only-ct':>8} {'only-k':>8} {'Jaccard':>8}")
    for name, i in result["tracks"].items():
        out(f"{name[:18]:<18} {i['ref']:8.1f} {i['auto']:9.1f} {i['both']:8.1f} "
            f"{i['only_ct']:8.1f} {i['only_k']:8.1f} {pct(i['jaccard']):>8}")
    tt = result["total"]
    out(f"{'TOTAL':<18} {tt['ref']:8.1f} {tt['auto']:9.1f} {tt['both']:8.1f} "
        f"{tt['only_ct']:8.1f} {tt['only_k']:8.1f} {pct(j):>8}")
    if tt["ref"] and tt["auto"]:
        out(f"kuulas finds {tt['both'] / tt['ref']:.0%} of colab-transcribe's muted time; "
            f"{tt['only_k'] / tt['auto']:.0%} of kuulas's muted time colab-transcribe left open")
    out(f"disagreement runs: {csv_path}\nfull results:      {json_path}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("processed", type=Path)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--minutes", type=float, help="compare only the first N minutes")
    g.add_argument("--all", action="store_true", help="whole episode (default)")
    ap.add_argument("--podcast", type=Path, help="unused (kept for symmetry)")
    ap.add_argument("--work", type=Path)
    ap.add_argument("--allow-download", action="store_true",
                    help="read media that are cloud placeholders (makes Dropbox fetch them)")
    a = ap.parse_args()
    for d in (a.input, a.processed):
        if not (d.resolve() / "project.sqlite").is_file():
            raise SystemExit(f"no project.sqlite in {d}")
    work = a.work or Path(tempfile.mkdtemp(prefix="wp85-compare-"))
    run(a.input.resolve(), a.processed.resolve(), work, a.minutes, a.allow_download)


if __name__ == "__main__":
    main()
