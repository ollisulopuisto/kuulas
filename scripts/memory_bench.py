"""Peak memory of kuulas's heavy paths on a long synthetic project (docs/MEMORY.md).

    uv run python scripts/memory_bench.py [--minutes 47] [--tracks 5] [--dir DIR]

Makes ``--tracks`` mono 48 kHz noise files of ``--minutes`` each (speakers take
turns, so the speech analysis has talk to find), imports them into a new
project, then runs each path in a FRESH Python process and prints its peak RSS
(``ru_maxrss``) and its RSS after start-up. A fresh process per path is what the
analysis worker is, so the worker rows are the worker's own peak. Caches that
the path would fill (envelopes, loudness curves, peaks) are deleted before it
runs, so every row is a cold run. No audio is played.

Needs ~0.3 GB of disk per track per 47 minutes (16-bit files plus the
project's working copies). Not part of ``pytest``: the bounded working set is
tested on short material in ``tests/test_memory_ceiling.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RATE = 48000

CHILD = r"""
import json, os, resource, shutil, sys, time
from pathlib import Path
os.environ.setdefault("KUULAS_ANALYSIS", "inline")
step, project, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
from kuulas import analysis, export, loudness_curve, memory, offload
from kuulas.session import Session
offload.MODE = "inline"

def rss_now():
    from kuulas import rss
    return rss.current()

def peak():
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw if sys.platform == "darwin" else raw * 1024

if step == "import":
    src = Path(sys.argv[4])
    start = rss_now()
    s = Session(project, rate=48000)
    t0 = time.monotonic()
    s.import_media(sorted(str(p) for p in src.glob("*.wav")))
else:
    s = Session(project)
    p, store = s.state, s.store
    caches = project / "caches"
    for sub in ("analysis",):
        shutil.rmtree(caches / sub, ignore_errors=True)
    if step == "peaks":
        shutil.rmtree(caches / "peaks", ignore_errors=True)
        for f in (project / "media").glob("*.npy"):
            f.unlink()
    store.budget = memory.MemoryBudget(memory.DEFAULT_LIMIT)  # cold: a new process
    start = rss_now()
    t0 = time.monotonic()
    if step == "baseline":
        pass
    elif step == "peaks":
        for m in p.media:
            store.pyramid(m.id)
    elif step == "lanes":
        analysis.speech_lanes(p, store)
    elif step == "silence":
        analysis.silence_ranges(p, store)
    elif step == "automix":
        analysis.automix(p, store)
    elif step == "curves":
        loudness_curve.project_curves(p, store, caches)
    elif step == "export_mix":
        export.run(s, s.mix_export_args({"folder": str(out), "format": "wav"}))
    elif step == "export_master":
        export.run(s, s.mix_export_args({"folder": str(out), "format": "wav",
                                         "master_lufs": -16.0}))
    elif step == "export_tracks":
        export.run(s, s.tracks_export_args({"folder": str(out)}))
    else:
        raise SystemExit(f"unknown step {step}")
wall = time.monotonic() - t0
print(json.dumps({"step": step, "start": start, "peak": peak(), "end": rss_now(),
                  "wall": wall, "budget_used": memory.BUDGET.used}))
s.close()
"""

STEPS = ["import", "baseline", "peaks", "lanes", "silence", "automix", "curves",
         "export_mix", "export_master", "export_tracks"]


def make_sources(folder: Path, minutes: float, tracks: int) -> None:
    import numpy as np  # noqa: PLC0415 - only the parent needs it
    import soundfile as sf  # noqa: PLC0415

    folder.mkdir(parents=True, exist_ok=True)
    frames = round(minutes * 60 * RATE)
    rng = np.random.default_rng(1)
    # Turns of 2 to 10 s, rotating among the speakers; the others' mics hear
    # the talker as bleed 20 dB down, over a -50 dBFS room.
    turns, at = [], 0
    while at < frames:
        n = int(rng.uniform(2, 10) * RATE)
        turns.append((at, min(frames, at + n), int(rng.integers(tracks))))
        at += n
    block = 60 * RATE
    for i in range(tracks):
        path = folder / f"speaker{i + 1}.wav"
        with sf.SoundFile(path, "w", RATE, 1, subtype="PCM_16") as f:
            for first in range(0, frames, block):
                count = min(block, frames - first)
                gain = np.full(count, 0.003, dtype=np.float32)
                for a, b, who in turns:
                    lo, hi = max(a, first), min(b, first + count)
                    if hi > lo:
                        gain[lo - first:hi - first] = 0.2 if who == i else 0.02
                noise = rng.standard_normal(count).astype(np.float32)
                f.write(noise * gain)


def run_step(step: str, project: Path, out: Path, src: Path) -> dict:
    argv = [sys.executable, "-c", CHILD, step, str(project), str(out), str(src)]
    t0 = time.monotonic()
    done = subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603 - our own interpreter and script
    if done.returncode:
        return {"step": step, "error": done.stderr.strip()[-600:],
                "wall": time.monotonic() - t0}
    return json.loads(done.stdout.strip().splitlines()[-1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=47.0)
    ap.add_argument("--tracks", type=int, default=5)
    ap.add_argument("--dir", type=Path, default=None)
    ap.add_argument("--steps", default=",".join(STEPS))
    args = ap.parse_args()
    base = args.dir or Path(tempfile.mkdtemp(prefix="kuulas-membench-"))
    src, project, out = base / "src", base / "Bench.kuulas", base / "out"
    if not src.exists():
        make_sources(src, args.minutes, args.tracks)
    if "import" in args.steps.split(",") and project.exists():
        shutil.rmtree(project)
    gib = 1024 ** 3
    print(f"{args.tracks} tracks x {args.minutes} min, 48 kHz mono, in {base}")
    print(f"{'step':<15} {'start GiB':>9} {'peak GiB':>9} {'end GiB':>8} {'wall s':>7}")
    for step in args.steps.split(","):
        r = run_step(step, project, out, src)
        if "error" in r:
            print(f"{step:<15} FAILED after {r['wall']:.0f} s: {r['error']}")
            continue
        print(f"{step:<15} {r['start'] / gib:9.2f} {r['peak'] / gib:9.2f} "
              f"{(r['end'] or 0) / gib:8.2f} {r['wall']:7.1f}", flush=True)
        shutil.rmtree(out, ignore_errors=True)
    if args.dir is None:
        shutil.rmtree(base, ignore_errors=True)
    return 0


if __name__ == "__main__":
    os.environ.setdefault("KUULAS_ANALYSIS", "inline")
    sys.exit(main())
