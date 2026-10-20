"""Acceptance: a long 5-track project fits in memory (docs/MEMORY.md).

Run by hand (tests/manual is not in the default run), minutes of CPU and
gigabytes of disk:

    uv run pytest -q tests/manual/test_memory_acceptance.py
    KUULAS_MEMORY_MINUTES=10,30,90 uv run pytest -q tests/manual/test_memory_acceptance.py

For each length (default 10 and 30 minutes) it writes 5 stereo 24-bit 48 kHz
noise files with speakers taking turns, and runs ONE editor process (a fresh
Python, as the app is) through: import, the waveform peaks of every file,
playback read-ahead through the whole programme (the engine's helper, no audio
device), the loudness curves and Auto-Silence in the real analysis worker, and
an export of the mix. It asserts the editor's peak RSS and the worker's, and
that the editor's peak does not grow with the length (the slope between the
shortest and the longest run). The always-on, short version of the growth
check is ``tests/test_memory_ceiling.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

pytestmark = pytest.mark.slow

RATE = 48000
TRACKS = 5
EDITOR_MAX = int(2.5 * 1024**3)
WORKER_MAX = 600 * 1024**2
#: Growth of the editor's peak per second of programme. The audio itself is
#: 5 tracks x 2 channels x 4 B x 48 kHz = 1.9 MB/s; the level envelopes are
#: 5 x 6.4 KB/s. Anything near the audio rate is a whole-file path.
MAX_SLOPE = 100 * 1024

CHILD = r"""
import json, sys, time
from pathlib import Path
from kuulas import engine as engine_mod, export, memory, offload, rss
from kuulas.engine import Engine
from kuulas.session import Session
src, project, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
offload.MODE = "process"
stages = {}
def stage(name):
    stages[name] = {"rss": rss.current(), "peak": rss.peak()}
s = Session(project, rate=48000)
s.import_media(sorted(str(p) for p in src.glob("*.wav")))
stage("import")
p, store = s.state, s.store
for m in p.media:
    store.pyramid(m.id)
stage("peaks")
e = Engine(s, background=False)
step = round(engine_mod.TICK_S * 4 * p.rate)  # one second of play per helper tick
ahead = round(engine_mod.PREFETCH_S * p.rate)
for first in range(0, p.length, step):
    e._fill_windows([(first, first + ahead)], evict=True)
stage("play_through")
offload.call("project_curves", p, store, store.cache_root, pause=False)
stage("curves")
offload.call("silence_ranges", p, store, pause=False)
stage("silence")
export.run(s, s.mix_export_args({"folder": str(out), "format": "wav"}))
stage("export_mix")
print(json.dumps({"stages": stages, "peak": rss.peak(),
                  "worker_max": offload.WORKER_PEAKS["max"],
                  "chunks": memory.BUDGET.namespace_bytes("chunks"),
                  "budget": memory.BUDGET.used}))
s.close()
"""


def write_sources(folder: Path, minutes: float) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    frames = round(minutes * 60 * RATE)
    rng = np.random.default_rng(7)
    turns, at = [], 0
    while at < frames:
        n = int(rng.uniform(2, 10) * RATE)
        turns.append((at, min(frames, at + n), int(rng.integers(TRACKS))))
        at += n
    block = 60 * RATE
    for i in range(TRACKS):
        with sf.SoundFile(folder / f"speaker{i + 1}.wav", "w", RATE, 2,
                          subtype="PCM_24") as f:
            for first in range(0, frames, block):
                count = min(block, frames - first)
                gain = np.full(count, 0.003, dtype=np.float32)
                for a, b, who in turns:
                    lo, hi = max(a, first), min(b, first + count)
                    if hi > lo:
                        gain[lo - first:hi - first] = 0.2 if who == i else 0.02
                noise = rng.standard_normal((count, 2)).astype(np.float32)
                f.write(noise * gain[:, None])


def run_editor(tmp: Path, minutes: float) -> dict:
    base = tmp / f"m{minutes:g}"
    write_sources(base / "src", minutes)
    done = subprocess.run(  # noqa: S603 - our own interpreter and script
        [sys.executable, "-c", CHILD, str(base / "src"), str(base / "P.kuulas"),
         str(base / "out")], capture_output=True, text=True, check=False,
        env={**os.environ, "KUULAS_ANALYSIS": "process"})
    assert done.returncode == 0, done.stderr[-2000:]
    result = json.loads(done.stdout.strip().splitlines()[-1])
    print(f"\n{minutes:g} min: " + json.dumps(result))
    return result


def test_a_long_project_fits(tmp_path):
    minutes = [float(m) for m in
               os.environ.get("KUULAS_MEMORY_MINUTES", "10,30").split(",")]
    results = {m: run_editor(tmp_path, m) for m in minutes}
    for m, r in results.items():
        assert r["peak"] <= EDITOR_MAX, f"{m} min: editor peak {r['peak']}"
        assert 0 < r["worker_max"] <= WORKER_MAX, f"{m} min: worker {r['worker_max']}"
    short, long = min(minutes), max(minutes)
    slope = (results[long]["peak"] - results[short]["peak"]) / ((long - short) * 60)
    assert slope < MAX_SLOPE, f"editor peak grows {slope:.0f} B per second of programme"
