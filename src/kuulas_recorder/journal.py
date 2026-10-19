"""The take's record on disk: ``<take>.take.json`` and ``<take>.journal.jsonl``.

``<take>.take.json`` is the snapshot the editor reads: where the take sits on
the recording clock, its segments and files, gaps, markers and counters. It is
replaced atomically (write a temporary file, fsync, rename, fsync the folder)
at every flush, so it is always a whole, valid JSON file.

``<take>.journal.jsonl`` is append-only, one JSON object per line, fsynced per
line: everything that happened, in order (started, mark, gap, device_lost,
worker_restarted, warnings, stopped). A crash can cut its last line short;
readers skip a line that does not parse.

The WAV files are the truth for how much audio there is: after a crash the
snapshot may lag the files by one flush, and recovery reads the files.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from kuulas_recorder import TAKE_FORMAT, version
from kuulas_recorder import names as naming
from kuulas_recorder.wavfile import WavRepairError, repair_wav, sync_dir

# Frames per second to flicks (1/705 600 000 s): exact for 48 kHz and every
# common rate. The editor's recording clock (WP30) counts in flicks.
FLICKS = 705_600_000
# Overflow positions are kept up to this many; the count goes on.
MAX_OVERFLOW_POSITIONS = 1000


def utc_iso(ns: int | None = None) -> str:
    t = time.time_ns() if ns is None else ns
    dt = datetime.fromtimestamp(t / 1e9, UTC)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    payload = json.dumps(data, indent=1, ensure_ascii=False).encode()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        view = memoryview(payload)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    sync_dir(path.parent)


class TakeRecord:
    """One take's snapshot and journal, owned by the supervisor."""

    def __init__(self, folder: Path | str, take: str, data: dict):
        self.folder = Path(folder)
        self.take = take
        self.data = data

    @classmethod
    def new(cls, folder: Path | str, take: str, *, rate: int, device: dict,
            channels: list[int], names: list[str]) -> TakeRecord:
        data = {
            "format": TAKE_FORMAT,
            "recorder_version": version(),
            "take": take,
            "state": "recording",
            "stop_reason": None,
            "created_utc": utc_iso(),
            "updated_utc": utc_iso(),
            "start_utc": None,
            "start_monotonic_ns": None,
            "rate": rate,
            "sample_format": "pcm_s24le",
            "device": device,
            "channels": [{"channel": c, "name": n}
                         for c, n in zip(channels, names, strict=True)],
            "segments": [],
            # Frames at the start of the take that were heard before Record was
            # pressed (WP12c pre-roll): Record was pressed at this frame.
            "preroll_frames": 0,
            "frames": 0,
            "gaps": [],
            "dropouts": [],
            "overflows": 0,
            "overflow_at": [],
            "markers": [],
            "worker_restarts": 0,
        }
        return cls(folder, take, data)

    @classmethod
    def load(cls, folder: Path | str, take: str) -> TakeRecord:
        path = Path(folder) / naming.sidecar_file(take)
        return cls(folder, take, json.loads(path.read_text(encoding="utf-8")))

    @property
    def sidecar(self) -> Path:
        return self.folder / naming.sidecar_file(self.take)

    @property
    def journal_path(self) -> Path:
        return self.folder / naming.journal_file(self.take)

    @property
    def started(self) -> bool:
        """The first block arrived: the take is on the recording clock."""
        return self.data["start_monotonic_ns"] is not None

    @property
    def names(self) -> list[str]:
        return [c["name"] for c in self.data["channels"]]

    @property
    def rate(self) -> int:
        return int(self.data["rate"])

    # --- segments ---------------------------------------------------------------

    def segment(self, n: int) -> dict | None:
        for s in self.data["segments"]:
            if s["segment"] == n:
                return s
        return None

    def add_segment(self, n: int, files: dict[str, str]) -> dict:
        seg = {"segment": n, "start_frame": None, "start_flicks": None,
               "files": {name: {"file": f, "frames": 0} for name, f in files.items()},
               "end": None}
        self.data["segments"].append(seg)
        return seg

    @staticmethod
    def segment_frames(seg: dict) -> int:
        return max((f["frames"] for f in seg["files"].values()), default=0)

    def segment_end(self, seg: dict) -> int:
        return (seg["start_frame"] or 0) + self.segment_frames(seg)

    def place_segment(self, seg: dict, start_frame: int) -> None:
        seg["start_frame"] = int(start_frame)
        seg["start_flicks"] = int(start_frame) * FLICKS // self.rate

    def last_end(self, before: int | None = None) -> int:
        """End frame of the last placed segment (before segment ``before``)."""
        end = 0
        for s in self.data["segments"]:
            if before is not None and s["segment"] >= before:
                continue
            if s["start_frame"] is not None:
                end = max(end, self.segment_end(s))
        return end

    def update_frames(self) -> None:
        self.data["frames"] = self.last_end()

    def next_segment_number(self) -> int:
        """One past every segment listed and every segment file on disk, so a
        file is never reused even if the snapshot missed it."""
        n = max((s["segment"] for s in self.data["segments"]), default=0) + 1
        while any((self.folder / naming.segment_file(self.take, name, n)).exists()
                  for name in self.names):
            n += 1
        return n

    def files_on_disk(self) -> dict[int, dict[str, str]]:
        """Every segment file that exists, listed or not (recovery)."""
        found: dict[int, dict[str, str]] = {}
        listed = {s["segment"] for s in self.data["segments"]}
        top = max(listed, default=0) + 2
        n = 1
        while n <= top:
            for name in self.names:
                f = naming.segment_file(self.take, name, n)
                if (self.folder / f).exists():
                    found.setdefault(n, {})[name] = f
                    top = max(top, n + 2)
            n += 1
        return found

    def repair_segment(self, seg: dict) -> list[dict]:
        """Repair each file of ``seg`` and set its frames from the file itself."""
        out = []
        for info in seg["files"].values():
            path = self.folder / info["file"]
            if not path.exists():
                info["frames"] = 0
                out.append({"file": info["file"], "frames": 0, "missing": True})
                continue
            try:
                r = repair_wav(path, rate=self.rate)
            except (OSError, WavRepairError) as e:
                out.append({"file": info["file"], "error": str(e)})
                continue
            info["frames"] = r.frames
            out.append({"file": info["file"], "frames": r.frames, "changed": r.changed,
                        "trimmed_bytes": r.trimmed_bytes})
        return out

    # --- writing ----------------------------------------------------------------

    def save(self) -> None:
        self.update_frames()
        self.data["updated_utc"] = utc_iso()
        atomic_write_json(self.sidecar, self.data)

    def journal(self, event: str, **fields) -> None:
        line = {"utc": utc_iso(), "event": event, **fields}
        data = (json.dumps(line, ensure_ascii=False) + "\n").encode()
        fd = os.open(self.journal_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, data)
            with contextlib.suppress(OSError):
                os.fsync(fd)
        finally:
            os.close(fd)


def read_journal(path: Path | str) -> list[dict]:
    """Every whole line of a journal; a line cut short by a crash is skipped."""
    out = []
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return out
    for line in text.splitlines():
        with contextlib.suppress(ValueError):
            out.append(json.loads(line))
    return out
