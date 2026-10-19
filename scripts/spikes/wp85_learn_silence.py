# ruff: noqa: E501, PLC0415, N806  (one-off spike, not product code)
"""WP85 spike: learn a per-track silence threshold from the hand-made mutes
of a kuulas project, read-only, and compare it with Auto-Silence.

    uv run python scripts/spikes/wp85_learn_silence.py PROJECT.kuulas \
        [--podcast /private/tmp/podcast-main] [--minutes 3] [--work DIR]

Read-only by construction: only ``project.sqlite`` (plus a ``-wal`` file if
there is one) and ``manifest.json`` are COPIED into a new empty directory
(``--work``, default a fresh temp dir) and opened there with
``History(read_only=True)``. The project folder itself is never opened by
kuulas code, so no lock, backup, -wal/-shm or cache is written in it. Audio
is read with soundfile from where the media rows say it is (linked files in
place, or ``media/<id>.flac`` inside the package), read mode only. Nothing
is uploaded.

What it prints, per speech track:
1. the hand-made muted stretches (runs of ``Clip.muted``), seconds, how
   many fall in the first ``--minutes``;
2. how many transcript words each media has (seconds on the media clock);
3. podcast ``silencelearn.calibrate`` (in process, from the podcast
   checkout's ``packages/silencelearn/src``; kuulas's pyproject untouched),
   with words and words-free;
4. the podcast session's proposed rule on kuulas's own measure (20 ms hops,
   ``analysis.track_levels``): T = p90(smooth(db over muted clips)) + 1 dB,
   guard T < median(smooth(db over unmuted)) - 3 dB; against the current
   threshold floor + ``grid.FLOOR_MARGIN_DB``: fraction of unmuted hops "on"
   under each, and the longest stretches where they disagree;
5. Auto-Silence (``analysis.silence_ranges``, on the project with every
   clip unmuted, i.e. what it would close if nobody had muted anything),
   current floor versus learned floor, seconds closed in the first
   ``--minutes`` and their overlap with the hand-made mutes.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np
from _readonly import (
    ReadOnlyStore,
    all_unmuted,
    clip_to,
    media_paths,
    mmss,
    muted_runs,
    open_copy,
    overlap,
    runs,
    ungated,
)
from speechmix import grid
from speechmix.stems import Lanes

from kuulas import analysis
from kuulas.clock import FLICKS

MIN_MUTED_S = 3.0
GUARD_DB = 3.0
P_MUTED = 90.0
MARGIN_DB = 1.0


def lanes_with(floors: dict[str, float]):
    """``analysis.speech_lanes`` with a per-track floor override (by track id)."""
    def speech_lanes(p, store):
        tracks = [t for t in p.tracks if t.kind == "speech" and not t.mute and t.clips]
        order, parts = [], {}
        for t in tracks:
            db, valid = analysis.track_levels(p, store, t)
            floor = floors.get(t.id, grid.noise_floor(grid.smooth(db), valid))
            spk = t.speaker or t.name
            if spk not in parts:
                order.append(spk)
                parts[spk] = []
            parts[spk].append((db, valid, floor, grid.FLOOR_MARGIN_DB, 0.0))
        return Lanes(speakers=[grid.lane(s, parts[s]) for s in order])
    return speech_lanes


# -- main ----------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    ap.add_argument("--podcast", type=Path, default=Path("/private/tmp/podcast-main"))
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--work", type=Path)
    ap.add_argument("--allow-download", action="store_true",
                    help="read media that are cloud placeholders (makes Dropbox fetch them)")
    a = ap.parse_args()
    project = a.project.resolve()
    if not (project / "project.sqlite").is_file():
        raise SystemExit(f"no project.sqlite in {project}")
    work = a.work or Path(tempfile.mkdtemp(prefix="wp85-")) / "copy"
    h = open_copy(project, work)
    print(f"metadata copied to {work} (original folder not opened)")
    p = h.state
    rate = p.rate
    window = round(a.minutes * 60 * rate)
    paths, problems = media_paths(h, project, a.allow_download)
    for line in problems:
        print("MEDIA", line)

    speech = [t for t in p.tracks if t.kind == "speech" and t.clips]
    horizon = max((b for t in speech for _a, b in muted_runs(t)), default=0)
    print(f"rate {rate}, length {p.length / rate:.1f} s, horizon (end of last hand-made "
          f"mute) {mmss(horizon / rate)}, window first {a.minutes:g} min")

    # 1 + 2
    words = {}
    for m, ws in h.transcripts().items():
        words[m] = [(w["s"] / FLICKS, (w["e"] - w["s"]) / FLICKS) for w in ws
                    if "s" in w and "e" in w]
    print("\n== 1/2. hand-made mutes and words")
    for t in speech:
        r = muted_runs(t)
        inwin = clip_to(r, 0, window)
        media = sorted({c.media for c in t.clips})
        print(f"[{t.name}] speaker={t.speaker!r} {len(r)} muted runs, "
              f"{sum(b - a for a, b in r) / rate:.1f} s; in window {len(inwin)} runs "
              f"{sum(b - a for a, b in inwin) / rate:.1f} s; words "
              + ", ".join(f"{m}:{len(words.get(m, []))}" for m in media))
        for x, y in r[:40]:
            print(f"    {mmss(x / rate)} - {mmss(y / rate)}  ({(y - x) / rate:.2f} s)")
        if len(r) > 40:
            print(f"    ... {len(r) - 40} more")
    if any(c.media not in paths for t in speech for c in t.clips):
        print("\nSTOP: audio for a speech track is missing here; steps 3-5 need it.")
        return
    store = ReadOnlyStore(paths, rate)

    # 3. silencelearn
    sys.path.insert(0, str(a.podcast / "packages" / "silencelearn" / "src"))
    import silencelearn as sl

    tracks = [sl.Track(t.name, [sl.Region(c.media, c.start / rate, c.length / rate,
                                          c.offset / rate, c.muted) for c in t.clips])
              for t in speech]

    class Source:
        def __init__(self, with_words):
            self.with_words = with_words

        def words(self, ref):
            return words.get(ref, []) if self.with_words else []

        def level(self, ref, s, e):
            return store.dbfs(ref, s, e)

        def missing(self):
            return False

    print(f"\n== 3. silencelearn (horizon {sl.horizon(tracks):.1f} s; window "
          f"{sl.WINDOW}s/{sl.HOP}s, p{sl.PERCENTILE:g}+{sl.MARGIN_DB:g} dB; dBFS per window)")
    for label, ww in (("with words", True), ("words-free", False)):
        for name, c in sl.calibrate(tracks, Source(ww)).items():
            th = "-" if c.threshold is None else f"{c.threshold:.1f}"
            dom = "-" if c.dominance is None else f"{c.dominance:.1f}"
            p25 = "-" if c.speech_p25 is None else f"{c.speech_p25:.1f}"
            print(f"[{name}] {label}: threshold {th} dBFS, dominance {dom} dB, muted "
                  f"{c.muted_seconds:.1f} s/{c.frames} win, bleed {c.bleed_frames}, "
                  f"speech p25 {p25} {c.reason} {c.gap_note} {c.clamp_note}".rstrip())

    # 4. proposed rule on kuulas's measure
    print("\n== 4. kuulas measure (20 ms hops): current floor+12 vs learned T")
    pu = ungated(p)
    hop = analysis.hop_frames(rate)
    hz = int(np.ceil(horizon / hop))
    learned_floor: dict[str, float] = {}
    for t in speech:
        db, valid = analysis.track_levels(pu, store, t)
        sm = grid.smooth(db)
        floor = grid.noise_floor(sm, valid)
        cur = floor + grid.FLOOR_MARGIN_DB
        mt = replace(t, gate=(), clips=tuple(replace(c, muted=False)
                                             for c in t.clips if c.muted))
        mdb, mvalid = analysis.track_levels(replace(pu, tracks=(mt,)), store, mt)
        mvalid = mvalid.copy()
        mvalid[hz:] = False  # horizon
        msec = mvalid.sum() * hop / rate
        line = f"[{t.name}] muted {msec:.1f} s, floor {floor:.1f}, current thr {cur:.1f} dB"
        if msec < MIN_MUTED_S:
            print(line + " -> too little muted audio, keeps the current floor")
            continue
        T = float(np.percentile(grid.smooth(mdb)[mvalid], P_MUTED)) + MARGIN_DB
        med = float(np.median(sm[valid]))
        vh = valid.copy()
        vh[hz:] = False
        med_h = float(np.median(sm[vh])) if vh.any() else float("nan")
        ok = med - GUARD_DB > T
        line += (f", learned T {T:.1f} dB ({T - cur:+.1f}), unmuted median {med:.1f} "
                 f"(before horizon {med_h:.1f}: guard there "
                 f"{'passes' if med_h - GUARD_DB > T else 'rejects'})")
        on_cur = valid & (db > cur)
        on_new = valid & (db > T)
        n = max(1, valid.sum())
        nh = max(1, valid[:hz].sum())
        line += (f"\n    on (all unmuted): current {on_cur.sum() / n:.1%}, learned "
                 f"{on_new.sum() / n:.1%}; before horizon: {on_cur[:hz].sum() / nh:.1%} vs "
                 f"{on_new[:hz].sum() / nh:.1%}")
        if not ok:
            line += f"\n    GUARD: T >= median - {GUARD_DB:g} dB, rejected (keeps the current floor)"
        else:
            learned_floor[t.id] = T - grid.FLOOR_MARGIN_DB
        print(line)
        for lab, m in (("learned only", on_new & ~on_cur), ("current only", on_cur & ~on_new)):
            rr = sorted(runs(m), key=lambda r: r[0] - r[1])[:5]
            tot = m.sum() * hop / rate
            print(f"    {lab} on: {tot:.1f} s; longest: " + ", ".join(
                f"{mmss(x * hop / rate)}+{(y - x) * hop / rate:.2f}s" for x, y in rr))

    # 5. Auto-Silence in the window
    print(f"\n== 5. closed in the first {a.minutes:g} min (project with every clip unmuted)")
    pa = all_unmuted(p)
    cur_gate = analysis.silence_ranges(pa, store)
    orig = analysis.speech_lanes
    try:
        analysis.speech_lanes = lanes_with(learned_floor)
        new_gate = analysis.silence_ranges(pa, store)
    finally:
        analysis.speech_lanes = orig
    for t in speech:
        hand = clip_to(muted_runs(t), 0, window)
        hs = sum(b - x for x, b in hand) / rate
        out = [f"[{t.name}] hand {hs:.1f} s"]
        for lab, g in (("auto now", cur_gate), ("auto learned", new_gate)):
            r = clip_to(g.get(t.id, ()), 0, window)
            s = sum(b - x for x, b in r) / rate
            ov = overlap(r, hand) / rate
            out.append(f"{lab} {s:.1f} s (covers {ov:.1f} s of hand = "
                       f"{ov / hs if hs else 0:.0%}; {s - ov:.1f} s beyond)")
        print("; ".join(out) + ("" if t.id in learned_floor else "  [no learned floor]"))
    h.close()


if __name__ == "__main__":
    main()
