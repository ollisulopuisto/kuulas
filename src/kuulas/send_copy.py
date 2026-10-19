"""File > Send a copy… (WP32, docs/FORMAT.md "Hand-off copy").

A copy of the project for another person, with a choice of media:

* ``none``: no audio travels. The receiver's kuulas finds its own files again by
  SHA-256 (File > Locate media…). Media the project keeps in its own folder (it has no
  other file to find) travels whole anyway.
* ``used``: the parts the edit plays, each widened by a 2 s handle (the default).
  The copy keeps the same media ids and the same positions, so no step of the
  history and no transcript needs rewriting: a media file is written at its full
  length, with digital silence outside the carried parts (FLAC stores silence in
  almost no space). The row says so (``extra["partial_copy"]``), and Locate media…
  swaps in the whole file when the receiver has it (``MediaStore.relink``).
* ``all``: every file travels, linked files copied into ``media/linked/``.

Never the locks, backups or caches. The copy has the same project ``id`` and a
new ``copy`` id (the old one goes on the ``lineage``), and the sender's history
gets a ``sent`` checkpoint naming it. The sender's file paths are not sent.
"""

from __future__ import annotations

import json
import logging
import math
import secrets
import shutil
import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path

import numpy as np
import soundfile as sf

from . import db as dbm
from . import package
from .excerpt_plan import excerpt_ranges
from .messages import KuulasError, t
from .model import Project
from .safe_filename import safe_filename
from .unique_name import unique_name

log = logging.getLogger("kuulas.send_copy")

MODES = ("none", "used", "all")
#: Context kept around each used stretch, so a cut can still be moved a little.
HANDLE_SECONDS = 2.0
#: Frames moved at a time while a partial file is written.
BLOCK = 1 << 20
#: What an estimate assumes a carried frame costs: 24-bit, uncompressed. FLAC of
#: speech comes in lower, so the estimate is a ceiling.
BYTES_PER_SAMPLE = 3

Ranges = tuple[tuple[int, int], ...]


class SendCopyError(KuulasError, ValueError):
    """The copy cannot be made (a bad choice, no folder)."""


def used_ranges(project: Project, frames: Mapping[str, int],
                handle_seconds: float = HANDLE_SECONDS) -> dict[str, Ranges]:
    """Per media id, the source frames ``[first, last)`` the edit plays, widened by the
    handles, clamped to the media's ``frames`` and merged (``excerpt_plan``).

    A muted clip counts: unmuting it must not find silence. A media that no clip uses
    is absent."""
    rate = project.rate
    uses = []
    for track in project.tracks:
        for clip in track.clips:
            first = clip.offset - clip.xfade_in // 2
            last = clip.offset + clip.length + clip.xfade_out // 2
            uses.append((clip.media, first / rate, last / rate))
    plan = excerpt_ranges(uses, handle=handle_seconds,
                          duration={m: n / rate for m, n in frames.items()})
    out: dict[str, Ranges] = {}
    for media_id, spans in plan.items():
        limit = frames.get(media_id)
        merged = [(round(lo * rate), round(hi * rate)) for lo, hi in spans]
        if limit is not None:
            merged = [(a, min(b, limit)) for a, b in merged]
        out[media_id] = tuple((a, b) for a, b in merged if b > a)
    return out


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _own_files(store, media_id: str) -> list[Path]:
    """The files a working media lives in: its FLAC and any kept original."""
    found = [store.working_file(media_id)]
    found += sorted((store.folder / "originals").glob(f"{media_id}*"))
    return [p for p in found if p.is_file() and p.suffix != ".partial"]


def _classify(store, project: Project) -> dict:
    """Which media are linked and readable, linked and offline, or the project's own."""
    offline = set(store.missing())
    linked, gone, own = [], [], []
    for media_id in store.ids():
        if store.is_linked(media_id):
            (gone if media_id in offline else linked).append(media_id)
        else:
            own.append(media_id)
    frames = {m: store.meta(m)["source_frames"] for m in store.ids()}
    return {"linked": linked, "offline": gone, "own": own, "frames": frames,
            "ranges": used_ranges(project, frames)}


def plan(store, project: Project) -> dict:
    """What each choice would carry, for the dialog: ``{mode: {bytes, seconds, media}}``
    (``bytes`` is an upper bound for ``used``), the media that cannot be carried
    because their file is offline, and the handle length."""
    sorted_ = _classify(store, project)
    own_bytes = sum(_file_size(f) for m in sorted_["own"] for f in _own_files(store, m))
    seconds = 0.0
    used_bytes = 0
    carried = 0
    for media_id, spans in sorted_["ranges"].items():
        if media_id in sorted_["offline"]:
            continue
        carried += 1
        frames = sum(b - a for a, b in spans)
        seconds += frames / store.rate
        used_bytes += frames * store.meta(media_id)["channels"] * BYTES_PER_SAMPLE
    linked_bytes = sum(store.meta(m)["linked_size"] or 0 for m in sorted_["linked"])
    return {
        "none": {"bytes": own_bytes, "seconds": 0.0, "media": len(sorted_["own"])},
        "used": {"bytes": own_bytes + used_bytes, "seconds": seconds, "media": carried},
        "all": {"bytes": own_bytes + linked_bytes, "seconds": None,
                "media": len(sorted_["own"]) + len(sorted_["linked"])},
        "offline": [{"id": m, "name": store.meta(m)["name"]} for m in sorted_["offline"]],
        "handle_seconds": HANDLE_SECONDS,
    }


def _write_partial(store, media_id: str, ranges: Ranges, target: Path) -> None:
    """The media at its full length, with only ``ranges`` filled in."""
    meta = store.meta(media_id)
    channels, total = meta["channels"], meta["source_frames"]
    partial = target.with_name(target.name + ".partial")
    target.parent.mkdir(parents=True, exist_ok=True)

    def silence(out, count: int) -> None:
        while count > 0:
            step = min(count, BLOCK)
            out.write(np.zeros((step, channels), dtype=np.float32))
            count -= step

    try:
        with sf.SoundFile(str(partial), "w", store.rate, channels, subtype="PCM_24",
                          format="FLAC") as out:
            at = 0
            for first, last in ranges:
                silence(out, first - at)
                for pos in range(first, last, BLOCK):
                    count = min(BLOCK, last - pos)
                    out.write(np.ascontiguousarray(store.read(media_id, pos, count).T))
                at = last
            silence(out, total - at)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def _set_extra(rows: sqlite3.Connection, media_id: str, **keys) -> str:
    current = rows.execute("select extra from media where id=?", (media_id,)).fetchone()
    extra = json.loads((current[0] if current else None) or "{}")
    extra.update(keys)
    return json.dumps(extra, ensure_ascii=False)


def _line(store, media_id: str, **more) -> dict:
    return {"id": media_id, "name": store.meta(media_id)["name"], **more}


def make(store, freeze: Callable[[Path], tuple[Project, dict]], project_name: str,
         folder: str, media: str, new_copy: str) -> dict:
    """Write the copy and return its report.

    ``freeze(target)`` writes a consistent copy of the project database to ``target``
    and returns the project state and manifest that go with it; the caller holds its
    lock for that, so the copy is one moment of the project (and includes the ``sent``
    checkpoint it has just written)."""
    if media not in MODES:
        raise SendCopyError("error.send_copy.bad_media", media=str(media))
    if not isinstance(folder, str) or not folder.strip():
        raise SendCopyError("error.send_copy.no_folder")
    parent = Path(folder).expanduser()
    parent.mkdir(parents=True, exist_ok=True)
    stem = safe_filename(f"{project_name} copy")
    name = unique_name(stem, [p.stem for p in parent.glob("*.kuulas")])
    final = parent / f"{name}.kuulas"
    building = parent / f".{name}.kuulas.partial"
    shutil.rmtree(building, ignore_errors=True)
    report = {"carried": [], "relink": [], "unavailable": [], "partial": []}
    try:
        for sub in package.DIRS:
            (building / sub).mkdir(parents=True, exist_ok=True)
        project, manifest = freeze(building / "project.sqlite")
        sorted_ = _classify(store, project)
        rows = dbm.connect(building / "project.sqlite")
        try:
            with dbm.tx(rows):
                # The sender's file paths are private and of no use to the receiver.
                rows.execute("delete from media_paths")
                _carry(store, media, sorted_, rows, building, final, report)
            dbm.checkpoint(rows)
        finally:
            rows.close()
        lineage = [*manifest.get("lineage", []), manifest.get("copy", "")]
        package.write_manifest(building, {
            **manifest, "copy": new_copy, "lineage": [c for c in lineage if c],
            "written_by": f"kuulas {package.kuulas_version()}"})
        building.replace(final)
    except BaseException:
        shutil.rmtree(building, ignore_errors=True)
        raise
    report.update(path=str(final), copy=new_copy, media=media,
                  bytes=sum(f.stat().st_size for f in final.rglob("*") if f.is_file()))
    log.info(t("log.send_copy.made", path=str(final), media=media))
    return report


def _carry(store, media: str, sorted_: dict, rows: sqlite3.Connection, building: Path,
           final: Path, report: dict) -> None:
    ranges = sorted_["ranges"] if media == "used" else {}
    for media_id in sorted_["own"]:
        own_files = _own_files(store, media_id)
        if not own_files:
            report["unavailable"].append(_line(store, media_id))
            continue
        if media == "used":
            _partial(store, media_id, ranges.get(media_id, ()), None, rows, building,
                     report)
            continue
        for source in own_files[:None if media == "all" else 1]:
            target = building / source.relative_to(store.folder.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        report["carried"].append(_line(store, media_id))
    for media_id in sorted_["offline"]:
        if media != "none":
            report["unavailable"].append(_line(store, media_id))
    for media_id in sorted_["linked"]:
        meta = store.meta(media_id)
        if media == "all":
            leaf = f"{media_id}-{safe_filename(meta['name'])}"
            target = building / "media" / "linked" / leaf
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(store.linked_file(media_id), target)
            where = final / target.relative_to(building)
            rows.execute(
                "update media set linked_path=?, linked_mtime_ns=?, linked_package_rel=?,"
                " linked_series_rel=null where id=?",
                (str(where), target.stat().st_mtime_ns,
                 target.relative_to(building).as_posix(), media_id))
            report["carried"].append(_line(store, media_id))
        elif media == "used" and media_id in ranges:
            _partial(store, media_id, ranges[media_id], meta["linked_size"], rows,
                     building, report)
        else:
            report["relink"].append(_line(store, media_id))


def _partial(store, media_id: str, spans: Ranges, source_size: int | None,
             rows: sqlite3.Connection, building: Path, report: dict) -> None:
    _write_partial(store, media_id, spans, building / "media" / f"{media_id}.flac")
    extra = _set_extra(rows, media_id, partial_copy={
        "ranges": [list(span) for span in spans], "source_size": source_size,
        "handle_seconds": HANDLE_SECONDS})
    rows.execute(
        "update media set storage='working', linked_path=null, linked_size=null,"
        " linked_mtime_ns=null, linked_package_rel=null, linked_series_rel=null,"
        " subtype='PCM_24', lossless=0, extra=? where id=?", (extra, media_id))
    seconds = math.fsum((b - a) for a, b in spans) / store.rate
    line = _line(store, media_id, seconds=seconds)
    report["carried"].append(line)
    report["partial"].append(line)


def new_copy_id() -> str:
    return secrets.token_hex(16)
