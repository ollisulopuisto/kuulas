# ruff: noqa: E501  (one-off spike helpers, not product code)
"""Read-only helpers shared by the WP85 spike scripts.

Metadata is COPIED into a new empty directory and opened there; the
project folder itself is never opened by kuulas code (no lock, no -wal/-shm,
no cache written in it). Audio is read with soundfile in read mode only.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf

from kuulas.history import History
from kuulas.model import Project, Track

SF_DATALESS = 0x40000000  # macOS: a cloud placeholder (Dropbox "online only")


def copy_metadata(project: Path, work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=False)  # must be new and empty
    for name in ("project.sqlite", "project.sqlite-wal", "manifest.json"):
        src = project / name
        if src.is_file():
            shutil.copyfile(src, work / name)  # read of the original only
    db = work / "project.sqlite"
    if (work / "project.sqlite-wal").exists():
        con = sqlite3.connect(db)  # the copy, never the original
        con.execute("pragma wal_checkpoint(truncate)")
        con.close()
    return db


def placeholder(path: Path) -> bool:
    try:
        return bool(getattr(os.stat(path), "st_flags", 0) & SF_DATALESS)
    except OSError:
        return False


def resolve(project: Path, row: dict, seen: list[str]) -> Path | None:
    cands = []
    if row["storage"] == "linked":
        cands.append(row.get("linked_path"))
        rel = row.get("linked_package_rel")
        if rel:
            cands += [str(project / rel), str(project.parent / rel)]
        cands += seen
    else:
        cands += [str(project / "media" / f"{row['id']}.flac"),
                  str(project / "media" / "excerpts" / f"{row['id']}.flac")]
    for c in cands:
        if c and Path(c).is_file():
            return Path(c)
    return None


class ReadOnlyStore:
    """``mixer.Store`` over soundfile in read mode. No envelope provider, so
    ``analysis`` measures from audio (same numbers, WP36)."""

    def __init__(self, paths: dict[str, Path], rate: int):
        self.paths, self.rate, self.handles = paths, rate, {}
        self._lock = threading.Lock()  # analysis reads from a thread pool

    def _f(self, media_id):
        if media_id not in self.handles:
            f = sf.SoundFile(str(self.paths[media_id]), "r")
            if f.samplerate != self.rate:
                raise SystemExit(f"{self.paths[media_id]}: {f.samplerate} Hz, project {self.rate}")
            self.handles[media_id] = f
        return self.handles[media_id]

    def read(self, media_id, first, count):
        with self._lock:
            return self._read(media_id, first, count)

    def _read(self, media_id, first, count):
        f = self._f(media_id)
        out = np.zeros((f.channels, count), dtype=np.float32)
        lo, hi = max(0, first), min(f.frames, first + count)
        if hi > lo:
            f.seek(lo)
            out[:, lo - first:hi - first] = f.read(hi - lo, dtype="float32", always_2d=True).T
        return out

    def dbfs(self, media_id, start_s, end_s) -> float | None:
        a, b = round(start_s * self.rate), round(end_s * self.rate)
        if b <= a:
            return float("-inf")
        x = self.read(media_id, a, b - a).mean(axis=0).astype(np.float64)
        rms = float(np.sqrt(np.mean(x * x)))
        return 20 * np.log10(rms) if rms > 0 else float("-inf")


# -- helpers -------------------------------------------------------------------

def muted_runs(track: Track) -> list[tuple[int, int]]:
    spans = sorted((c.start, c.end) for c in track.clips if c.muted)
    out: list[list[int]] = []
    for a, b in spans:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def overlap(r1, r2) -> int:
    return sum(max(0, min(b, d) - max(a, c)) for a, b in r1 for c, d in r2)


def clip_to(ranges, lo, hi):
    return [(max(a, lo), min(b, hi)) for a, b in ranges if min(b, hi) > max(a, lo)]


def mmss(sec: float) -> str:
    return f"{int(sec // 60):02d}:{sec % 60:05.2f}"


def runs(mask: np.ndarray):
    m = np.concatenate(([False], mask, [False]))
    d = np.flatnonzero(np.diff(m.astype(np.int8)))
    return list(zip(d[::2], d[1::2], strict=True))


def ungated(p: Project) -> Project:
    return replace(p, tracks=tuple(replace(t, gate=()) for t in p.tracks))


def all_unmuted(p: Project) -> Project:
    return replace(p, tracks=tuple(
        replace(t, gate=(), clips=tuple(replace(c, muted=False) for c in t.clips))
        for t in p.tracks))


def open_copy(project: Path, work: Path) -> History:
    """Copy the metadata to ``work`` (new, must not exist) and open the copy."""
    return History(copy_metadata(project, work), read_only=True)


def media_paths(h: History, project: Path, allow_download: bool = False
                ) -> tuple[dict[str, Path], list[str]]:
    """``(media id -> readable file, problems)``. A Dropbox online-only
    placeholder is a problem unless ``allow_download``."""
    seen: dict[str, list[str]] = {}
    for sha, path in h.db.execute("select sha256, path from media_paths"):
        seen.setdefault(sha, []).append(path)
    paths: dict[str, Path] = {}
    problems: list[str] = []
    for row in h.media_rows():
        f = resolve(project, row, seen.get(row["sha256"], []))
        if f is None:
            problems.append(f"{row['name']}: not on this machine ({row.get('linked_path')})")
        elif placeholder(f) and not allow_download:
            problems.append(f"{row['name']}: Dropbox online-only placeholder ({f})")
        else:
            paths[row["id"]] = f
    return paths, problems
