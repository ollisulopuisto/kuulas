"""Export (WP11): three exports, one engine.

* **mix**: the programme as heard, the whole edit or a range;
* **selection**: a range of the mix with a short fade at each end;
* **tracks**: one file per track, all the same length and starting at the same
  moment, for mixing elsewhere.

``run`` is what ``Session.export`` calls. It takes a progress callback and a
cancel flag so the job runner (WP9) can wrap it later; it does not know about
jobs. Nothing reaches the target path until it is complete: every file is
written under a ``.partial`` name and renamed (ground rule 8), and a failure,
a cancel or a full disk removes what was started.

Blocks are rendered on a thread pool (numpy releases the GIL in the heavy
parts) and written in order, so a parallel render is byte-identical to a
serial one: every output frame depends only on its own timeline frame.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from speechmix import programme

from . import export_formats, export_names, mixer, priority, stem_ranges, transcript
from . import placeholders as placeholders_module
from .media import streaming
from .messages import KuulasError, t
from .model import Project, Track
from .package import kuulas_version
from .region_names import region_filenames

log = logging.getLogger("kuulas.export")

#: Blocks of this many seconds are rendered, in parallel, and written in order.
#: Each render of a block holds every track's clips as float64 stereo, and up
#: to 2 x workers blocks are in flight: at 30 s a 47-minute, 5-track mix
#: export peaked at 1.2 GB (docs/MEMORY.md, 2026-10-20), at 10 s ~0.5 GB.
BLOCK_SECONDS = 10
#: Mastering holds the whole programme in memory (float64 inside speechmix),
#: so longer than this is refused with a message (and see master_fits).
MAX_MASTER_SECONDS = 3 * 3600
#: What speechmix's ``programme.master`` holds per sample of the programme
#: (per channel): the float64 copy, the lifted signal, the peak stage's and
#: the limiter's per-sample curves and the round before. Measured 2026-10-20
#: (docs/MEMORY.md): a stereo master peaked 2.8 GB at 10 minutes and 5.0 GB
#: at 20, i.e. 38 B per sample per channel over a ~0.6 GB render, so a
#: 47-minute one needs ~11 GB and a 90-minute one ~21 GB: a 24 GB Mac swaps.
MASTER_BYTES_PER_SAMPLE = 40
#: The share of the computer's memory a master may take; longer is refused
#: with a message (export unmastered) instead of swapping the Mac to a halt.
#: On 24 GB that is ~55 minutes of stereo.
MASTER_MEMORY_SHARE = 0.5


def physical_memory() -> int:
    """Bytes of RAM in this computer (0 when the system does not say)."""
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return 0


def master_fits(frames: int, channels: int, physical: int | None = None) -> bool:
    """Whether mastering ``frames`` x ``channels`` stays inside
    ``MASTER_MEMORY_SHARE`` of the memory (unknown memory: allowed)."""
    physical = physical_memory() if physical is None else physical
    if physical <= 0:
        return True
    return frames * channels * MASTER_BYTES_PER_SAMPLE <= MASTER_MEMORY_SHARE * physical


def master_minutes_that_fit(channels: int, rate: int,
                            physical: int | None = None) -> int:
    physical = physical_memory() if physical is None else physical
    return int(MASTER_MEMORY_SHARE * physical
               / (channels * MASTER_BYTES_PER_SAMPLE * rate * 60))
#: A selection fades in and out over this long so its ends do not click. 30 ms
#: is the owner's choice (WP11): long enough to be click-free, too short to hear.
FADE_SECONDS = 0.030
#: Bump when a change to the exporter changes what the same edit renders to, so
#: "unchanged since vN" never claims a file the new code would not write.
RENDER_VERSION = 1
#: The 32-bit RIFF size limit, less room for the headers.
MAX_WAV_BYTES = 0xFFFFFFFF - 4096

#: File-name words the automixer (``podcast/apps/automixer``, ``MUSIC_WORDS``)
#: reads as "this is music, not speech". A music track whose name lacks one
#: gets " MUSIC" added to its file name, or it would be mixed as a voice.
MUSIC_WORDS = ("MUSIC", "THEME", "TUNNARI", "MUSA", "MUSIIKKI", "TUNNUS", "JINGLE")

KINDS = ("mix", "selection", "tracks")
#: Every format id the registry knows; which of them this machine can write is
#: ``export_formats.available_formats()``, checked in ``_settings``.
FORMATS = tuple(f.id for f in export_formats.ALL_FORMATS)
#: ``bit_depth`` 32 is float: what a bit-exact copy of the mix needs.
BIT_DEPTHS = (16, 24, 32)
PROCESSING = ("dry", "as_heard")

#: What each export starts from (owner, 2026-10-16); the last settings used
#: replace these, per kind and per project (ground rule 16).
DEFAULTS: dict[str, dict[str, Any]] = {
    "mix": {"format": "flac", "bit_depth": 24, "mp3_kbps": None, "master_lufs": None,
            "template": "{title} v{n}.{ext}", "latest": False},
    "selection": {"format": "mp3", "bit_depth": 24, "mp3_kbps": None,
                  "master_lufs": None,
                  "template": "{title} {from}\N{EN DASH}{to} v{n}.{ext}",
                  "latest": False},
    "tracks": {"format": "wav", "bit_depth": 24, "mp3_kbps": None,
               "template": "{title}{span} tracks v{n}", "processing": "dry",
               "list_file": False, "for_automixer": False},
}
#: What the one-button "Export all tracks" starts from. Dry stems with the edit
#: applied (cuts, clip gain, fades, mutes) and no bus or master: what a mixer
#: such as the automixer wants, which does its own processing. One folder per
#: run, named by project and local time, so nothing is overwritten.
ALL_TRACKS: dict[str, Any] = {
    "kind": "tracks", "format": "wav", "bit_depth": 24, "processing": "dry",
    "list_file": True, "template": "{title} {stamp} v{n}"}
#: What the one-button mix export starts from: the programme as heard, one file
#: in the exports folder, named by project and local time so no run overwrites another.
MIX_FILE: dict[str, Any] = {"kind": "mix", "template": "{title} {stamp} v{n}.{ext}"}
#: Settings that are not remembered: they are about this one export.
NOT_REMEMBERED = ("range", "for_automixer", "track_ids")
#: Settings that do not change the rendered audio, so they stay out of the hash.
NOT_HASHED = ("folder", "template", "latest")

Progress = Callable[[float, str], None]


class ExportError(KuulasError, RuntimeError):
    """The export cannot be made (or was cancelled); nothing was left behind."""


@dataclass
class _Tags:
    title: str
    album: str
    comment: str


class _WavWriter:
    """A WAV written block by block, with a ``bext`` chunk (Broadcast WAV).

    soundfile cannot write ``bext``, and a DAW that places files by their time
    reference needs it, so the header is written here. ``bit_depth`` 32 is
    float. Sizes are patched in when the file is closed.
    """

    BEXT_SIZE = 602  # EBU Tech 3285 v1: 256 + 32 + 32 + 10 + 8 + 8 + 2 + 64 + 190

    def __init__(self, path: Path, rate: int, channels: int, bit_depth: int,
                 time_reference: int, description: str):
        self.bit_depth, self.channels = bit_depth, channels
        self.frames = 0
        self.f = path.open("wb")
        now = datetime.now(UTC)
        bext = (_fixed(description, 256) + _fixed("kuulas", 32) + _fixed("", 32)
                + _fixed(now.strftime("%Y-%m-%d"), 10)
                + _fixed(now.strftime("%H:%M:%S"), 8)
                + struct.pack("<QH", time_reference, 1) + bytes(64 + 190))
        float_ = bit_depth == 32
        width = bit_depth // 8 * channels
        self.f.write(b"RIFF\0\0\0\0WAVE")
        self.f.write(b"bext" + struct.pack("<I", len(bext)) + bext)
        self.f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 3 if float_ else 1, channels,
                                           rate, rate * width, width, bit_depth))
        self.f.write(b"data\0\0\0\0")
        self.data_at = self.f.tell()

    def write(self, block: np.ndarray) -> None:
        """``block``: ``(channels, n)`` float, interleaved on the way out."""
        inter = np.ascontiguousarray(block.T, dtype=np.float32)
        if self.bit_depth == 32:
            raw = inter.tobytes()
        else:
            top = 2 ** (self.bit_depth - 1)
            ints = np.clip(np.rint(inter.astype(np.float64) * (top - 1)), -top, top - 1)
            ints = ints.astype("<i4")
            raw = (ints.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
                   if self.bit_depth == 24 else ints.astype("<i2").tobytes())
        self.f.write(raw)
        self.frames += inter.shape[0]

    def close(self, *, complete: bool = True) -> None:
        if complete:
            size = self.f.tell() - self.data_at
            if size % 2:  # RIFF chunks are padded to an even length
                self.f.write(b"\0")
            end = self.f.tell()
            # The RIFF size is the file length minus the 8-byte RIFF header. (It was once
            # computed inside the write() call, which moved the position to the end
            # first, so the field stayed 0 and the number was appended as stray bytes:
            # editors forgave it, macOS Quick Look and CoreAudio did not.)
            self.f.seek(4)
            self.f.write(struct.pack("<I", end - 8))
            self.f.seek(self.data_at - 4)
            self.f.write(struct.pack("<I", size))
            self.f.flush()
            os.fsync(self.f.fileno())
        self.f.close()


class _FlacWriter:
    """FLAC with its tags (soundfile writes Vorbis comments; no BWF here)."""

    def __init__(self, path: Path, rate: int, channels: int, bit_depth: int,
                 tags: _Tags):
        self.f = sf.SoundFile(path, "w", rate, channels, format="FLAC",
                              subtype=f"PCM_{bit_depth}")
        self.f.title, self.f.album, self.f.comment = tags.title, tags.album, tags.comment

    def write(self, block: np.ndarray) -> None:
        self.f.write(block.T)

    def close(self, *, complete: bool = True) -> None:  # noqa: ARG002 - same shape as WAV
        self.f.close()


def _fixed(text: str, size: int) -> bytes:
    """``text`` as a NUL-padded field of ``size`` bytes, cut on a character
    boundary (UTF-8 is what DAWs show, though the standard says ASCII)."""
    raw = text.encode("utf-8")[:size]
    raw = raw.decode("utf-8", errors="ignore").encode("utf-8")
    return raw + bytes(size - len(raw))


@dataclass
class _Job:
    """Everything one export needs, taken under the session lock."""

    kind: str
    settings: dict[str, Any]
    project: Project
    store: Any
    rate: int
    first: int  # timeline frame the output starts at
    frames: int  # how long it is
    ranged: bool
    edit: str
    project_name: str
    head: str
    digest: str
    #: Narration placeholders inside the exported range, which play as silence
    #: (WP43): reported, never a reason to refuse.
    placeholders: int = 0
    #: Local clock at the start, for names ("2026-10-18 14-30-12"): the one-button
    #: track export puts it in the folder name so no run overwrites another.
    stamp: str = ""
    #: Names of the tracks that come out as silence (muted, or not soloed).
    silent: tuple[str, ...] = ()
    #: The edit's id, to tell the main edit (named by the project alone) from another.
    edit_id: str = ""


# -- settings ------------------------------------------------------------------


def _fail(key: str, **params: Any) -> ExportError:
    return ExportError(key, **params)


def _settings(kind: str, remembered: dict | None, args: dict) -> dict[str, Any]:
    """Defaults, then the last settings of this kind, then ``args``; checked."""
    if kind not in KINDS:
        raise _fail("error.export.bad_kind", kind=kind)
    # track_ids: the stems to write, or (mix) the only tracks that are mixed.
    allowed = set(DEFAULTS[kind]) | {"folder", "track_ids"}
    remembered = dict(remembered or {})
    if args.get("kbps") is not None:  # the public name of ``mp3_kbps``
        args = {**args, "mp3_kbps": args["kbps"]}
    if "master_lufs" in args and args["master_lufs"] is None:
        remembered.pop("master_lufs", None)  # said "off": forget the remembered target
    if args.get("format") not in (None, remembered.get("format")):
        remembered.pop("mp3_kbps", None)  # a bitrate means little for another codec
    if isinstance(remembered.get("template"), str):  # an older built-in default
        remembered["template"] = export_names.migrate_template(remembered["template"])
    merged = {**DEFAULTS[kind], **{k: v for k, v in remembered.items() if k in allowed},
              **{k: v for k, v in args.items() if k in allowed and v is not None}}
    fmt = export_formats.get(merged["format"])
    if fmt is None:
        raise _fail("error.export.bad_format", format=merged["format"],
                    available=", ".join(f.id for f in export_formats.available_formats()))
    if merged["bit_depth"] not in BIT_DEPTHS:
        raise _fail("error.export.bad_bit_depth", bit_depth=merged["bit_depth"])
    if fmt.bit_depths and merged["bit_depth"] not in fmt.bit_depths:
        merged["bit_depth"] = 24  # FLAC has no float
    kbps = merged.get("mp3_kbps")
    if kbps is not None:
        low, high = fmt.kbps or (64, 320)
        if (not isinstance(kbps, int) or isinstance(kbps, bool)
                or (fmt.kbps and not low <= kbps <= high)):
            raise _fail("error.export.bad_kbps", kbps=kbps, low=low, high=high)
    lufs = merged.get("master_lufs")
    if kind == "tracks":
        merged.pop("master_lufs", None)  # a mastered stem would not sum to the mix
        if merged["processing"] not in PROCESSING:
            raise _fail("error.export.bad_processing", processing=merged["processing"])
    elif lufs is not None:
        try:
            merged["master_lufs"] = float(lufs)
        except (TypeError, ValueError):
            raise _fail("error.export.bad_lufs", value=lufs) from None
    rng = args.get("range")
    if rng is not None:
        try:
            a, b = (int(x) for x in rng)
        except (TypeError, ValueError):
            raise _fail("error.export.bad_range") from None
        merged["range"] = [a, b]
    elif kind == "selection":
        raise _fail("error.export.bad_range")
    merged["latest"] = bool(merged.get("latest", False))
    ids = merged.get("track_ids")
    if ids is not None and (
            not isinstance(ids, list) or not ids
            or not all(isinstance(i, str) for i in ids)):
        raise _fail("error.export.bad_tracks")
    if kind == "tracks":
        merged["for_automixer"] = bool(merged.get("for_automixer", False))
    return merged


def _exported(project: Project, settings: dict) -> list[Track]:
    """The tracks a track export writes: all of them, or the ``track_ids`` chosen
    (buses are never stems)."""
    ids = settings.get("track_ids")
    if ids is None:
        return list(project.tracks)
    return [tr for tr in project.tracks if tr.id in ids]


def _mixed_project(project: Project, settings: dict) -> Project:
    """What a mix of chosen ``track_ids`` renders: those tracks only. Mute and solo
    still decide what sounds as for the whole mix: when something is soloed, a kept
    track that is not soloed stays silent even if every soloed track was left out."""
    ids = settings.get("track_ids")
    if ids is None:
        return project
    soloing = any(tr.solo for tr in project.tracks)
    kept = tuple(replace(tr, mute=True) if soloing and not tr.solo and not tr.mute else tr
                 for tr in project.tracks if tr.id in ids)
    if soloing and not any(tr.solo for tr in kept):
        kept = tuple(replace(tr, mute=True) for tr in kept)
    return replace(project, tracks=kept)


def _check_tracks(project: Project, settings: dict) -> None:
    """Every chosen track must exist in this edit."""
    ids = settings.get("track_ids")
    if ids is not None and not set(ids) <= {tr.id for tr in project.tracks}:
        raise _fail("error.export.bad_tracks")


def options(kind: str, base: dict, args: dict) -> dict:
    """The arguments of a one-button export: ``base`` (``MIX_FILE`` or ``ALL_TRACKS``)
    plus what the caller chose. ``name`` is a file name the owner typed: it is taken
    literally, the range (if any) and ``v{n}`` follow it, so a name never overwrites."""
    keys = {"format", "bit_depth", "kbps", "folder", "range", "master_lufs", "track_ids"}
    chosen = {k: v for k, v in args.items() if k in keys and v is not None}
    out = {**base, **chosen}
    if kind == "mix":
        ext = ".{ext}"
        if "master_lufs" in args and args["master_lufs"] is None:
            out["master_lufs"] = None  # an explicit "off", not "say nothing"
    else:
        out.pop("master_lufs", None)
        ext = ""
    if args.get("name"):
        literal = str(args["name"]).replace("{", "{{").replace("}", "}}")
        out["template"] = f"{literal}{{span}}{{subset}} v{{n}}{ext}"
    elif chosen.get("range") is not None or chosen.get("track_ids") is not None:
        out["template"] = base["template"].replace(
            "{title}", "{title}{span}{subset}", 1).replace(
                "{edit}", "{edit}{span}{subset}", 1)
    return out


def _snapshot(session, kind: str, args: dict) -> _Job:
    with session.lock:
        h = session.history
        h._check_writable()  # Fail now, not after an hour of rendering.
        saved = h.meta_json("export", {})
        settings = _settings(kind, saved.get("settings", {}).get(kind), args)
        folder = settings.get("folder") or saved.get("folder")
        if not folder:
            folder = str(session.package.path.parent
                         / f"{session.package.path.stem} exports")
        settings["folder"] = str(folder)
        project = h.state
        _check_tracks(project, settings)
        rate = project.rate
        total = project.length
        if total <= 0:
            raise _fail("error.export.empty")
        first, frames, ranged = 0, total, False
        if "range" in settings:
            a, b = settings["range"]
            a, b = max(0, a), min(total, b)
            if b <= a:
                raise _fail("error.export.bad_range")
            first, frames, ranged = a, b - a, True
            settings["range"] = [a, b]
        edit = next((e["name"] for e in h.edits() if e["id"] == h.edit), h.edit)
        digest = _digest(project, kind, settings, h.edit_hash)
        unrecorded = len(placeholders_module.unrecorded(
            project.placeholders, first, first + frames))
        silent = tuple(tr.name for tr in _exported(project, settings)
                       if not _audible(project, tr))
        if kind != "tracks":
            project = _mixed_project(project, settings)
        return _Job(kind, settings, project, session.store, rate, first, frames, ranged,
                    edit, session.package.path.stem, h.head, digest, unrecorded,
                    export_names.stamp(datetime.now(UTC).astimezone()), silent, h.edit)


def _audible(project: Project, track: Track) -> bool:
    """Does the track sound in the programme? The mixer's rule: while anything is
    soloed only soloed tracks do, otherwise the mute switch decides, and a muted
    bus silences its tracks."""
    return track.id not in transcript.silent_tracks(project)


#: Fields that never change what any export sounds like: names (they only name files),
#: and in a project the markers, the narration placeholders' texts (a placeholder
#: plays as silence wherever it is) and ``mix_done`` (records about the edit, written
#: by commands that also change gains, which the key sees).
_AUDIO_SKIP = {"project": ("markers", "placeholders", "mix_done"),
               "track": ("name",), "clip": ("name",), "bus": ("name",)}
#: The last ``audio_key`` asked for, by the project object (frozen, so the same object
#: always has the same key). The live project is asked for on every state answer.
_audio_memo: tuple[Project, str] | None = None
_audio_lock = threading.Lock()


def audio_key(project: Project) -> str:
    """The key of what the project sounds like: equal key, equal audio in every export
    (the mix and every stem), so a render made from a snapshot with this key still
    matches the edit (``render_listen``).

    It changes with: clips (added, removed, moved, trimmed, split), their offsets, gains,
    pans, fades, crossfades, envelopes and mutes; tracks' gain, pan, mute, solo, gate,
    automation, kind (speech or music), speaker, bus, mono, ducking and role switches;
    buses' gain, pan, mute and role (``kind``: it changes which tracks are music stems);
    the master gain; the media's identities (content hash, frames, channels) and sync;
    the project rate; anything in a dataclass's ``extra`` (unknown, so counted).

    It does NOT change with: the playhead, the In/Out marks, the selection and every
    view setting (none of them is in the project), markers and regions, narration
    placeholders, the names of tracks, clips, buses and media, and ``mix_done``."""
    global _audio_memo  # noqa: PLW0603 - a one-entry memo, guarded by the lock
    with _audio_lock:
        memo = _audio_memo
        if memo is not None and memo[0] is project:
            return memo[1]
    d = project.to_dict()
    for key in _AUDIO_SKIP["project"]:
        d.pop(key, None)
    d["media"] = sorted([m["id"], m.get("sha256", ""), m["frames"], m["channels"],
                         m.get("excerpt_of"), m.get("excerpt_start_flicks", 0),
                         m.get("time_ref_flicks")] for m in d["media"])
    for track in d["tracks"]:
        for key in _AUDIO_SKIP["track"]:
            track.pop(key, None)
        for clip in track["clips"]:
            for key in _AUDIO_SKIP["clip"]:
                clip.pop(key, None)
    for bus in d["buses"]:
        for key in _AUDIO_SKIP["bus"]:
            bus.pop(key, None)
    key = hashlib.sha256(json.dumps(
        {"render": RENDER_VERSION, "audio": d}, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()
    with _audio_lock:
        _audio_memo = (project, key)
    return key


def _digest(project: Project, kind: str, settings: dict, edit_hash: str) -> str:
    """What the rendered audio depends on: the edit state, the media it plays
    (by content) and the settings that change the sound. Not the folder or the
    name, which only say where it goes."""
    material = {
        "render": RENDER_VERSION, "kind": kind, "edit": edit_hash, "rate": project.rate,
        "media": sorted((m.id, m.sha256, m.frames) for m in project.media),
        "settings": {k: v for k, v in sorted(settings.items()) if k not in NOT_HASHED},
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


# -- names ---------------------------------------------------------------------


def _safe(name: str) -> str:
    """A file name part: no separators or characters that file systems refuse."""
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .") or "_"


def _stamp(frames: int, rate: int) -> str:
    seconds = frames // rate
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def _name(job: _Job, n: int | str) -> str:
    """The template filled in. ``n`` may be ``"#"`` to name the series."""
    s = job.settings
    span = ""
    if job.ranged:
        a, b = s["range"]
        span = f" {_stamp(a, job.rate)}\N{EN DASH}{_stamp(b, job.rate)}"
    # Only some tracks (a selection): their names are in the file name too.
    subset = (f" ({', '.join(tr.name for tr in _exported(job.project, s))})"
              if s.get("track_ids") else "")
    fields = {"edit": _safe(job.edit), "title": _safe(_title(job)), "n": n,
              "ext": _format(job).ext, "span": span, "subset": subset,
              "project": _safe(job.project_name),
              "stamp": job.stamp}
    fields["from"] = _stamp(s["range"][0], job.rate) if job.ranged else "0m00s"
    fields["to"] = _stamp(s["range"][1], job.rate) if job.ranged else _stamp(
        job.frames, job.rate)
    try:
        return _safe(s["template"].format(**fields))
    except (KeyError, IndexError, ValueError):
        raise _fail("error.export.bad_template", template=s["template"]) from None


def _title(job: _Job) -> str:
    """The project, then the edit unless it is the main one (``export_names``)."""
    return export_names.title(job.project_name, job.edit_id, job.edit)


def _describe(job: _Job) -> str:
    s = job.settings
    if not _format(job).lossless:
        what = f"{s['format'].upper()} {_kbps(job, 2)} kbps"
    else:
        float32 = s["bit_depth"] == 32 and s["format"] == "wav"
        depth = "32-bit float" if float32 else f"{s['bit_depth']}-bit"
        what = f"{s['format'].upper()} {depth}"
    if job.kind == "tracks":
        return t("export.what.tracks", what=what,
                 processing=t(f"export.processing.{s['processing']}"))
    if job.kind == "selection":
        return t("export.what.selection", what=what)
    return what


def _format(job: _Job) -> export_formats.Format:
    fmt = export_formats.get(job.settings["format"])
    if fmt is None:  # checked in _settings; gone only if ffmpeg changed under us
        raise _fail("error.export.bad_format", format=job.settings["format"],
                    available=", ".join(f.id for f in export_formats.available_formats()))
    return fmt


def _kbps(job: _Job, channels: int) -> int:
    return job.settings.get("mp3_kbps") or _format(job).default_kbps(channels)


# -- rendering -----------------------------------------------------------------


def _edge_gain(first: int, count: int, total: int, fade: int) -> np.ndarray | None:
    """The 30 ms fade-in/out gains for frames ``[first, first+count)`` of
    ``total``, or None if this block lies between the fades."""
    if first >= fade and first + count <= total - fade:
        return None
    i = np.arange(first, first + count)
    gain = np.ones(count)
    head = i < fade
    gain[head] = np.sin(0.5 * np.pi * i[head] / fade) ** 2
    tail = i >= total - fade
    gain[tail] *= np.sin(0.5 * np.pi * (total - 1 - i[tail]) / fade) ** 2
    return gain


class _Cancel(Exception):  # noqa: N818 - control flow inside this module only
    pass


def _pump(total: int, rate: int, render: Callable[[int, int], np.ndarray],
          write: Callable[[np.ndarray], None], workers: int,
          cancel: threading.Event | None, tick: Callable[[float], None]) -> None:
    """Render blocks on ``workers`` threads and ``write`` them in order.

    At most ``2 * workers`` blocks are in flight, so memory is bounded however
    long the programme is. ``tick(fraction)`` is called after each write.

    Playback first (docs/PLAYBACK-PRIORITY.md): an export runs in the editor's
    process, so it pauses while audio plays. Every block, here and on the
    render threads, passes ``priority.checkpoint``: started as a job (the UI's
    exports are) it waits there; called by a request thread it does not.
    """
    step = max(1, round(BLOCK_SECONDS * rate))
    starts = iter(range(0, total, step))
    done = 0

    def check() -> None:
        try:
            priority.checkpoint(cancel)
        except priority.CancelledError:
            raise _Cancel from None
        if cancel is not None and cancel.is_set():
            raise _Cancel

    def gated_render(start: int, count: int) -> np.ndarray:
        check()
        # A scan from start to end: its audio is not kept (docs/MEMORY.md).
        with streaming():
            return render(start, count)

    if workers <= 1:
        for start in starts:
            count = min(step, total - start)
            write(gated_render(start, count))
            done += count
            tick(done / total)
        return
    pending: deque[Future] = deque()
    with priority.executor(workers, "kuulas-export") as pool:

        def feed() -> None:
            if (start := next(starts, None)) is not None:
                pending.append(pool.submit(gated_render, start, min(step, total - start)))

        try:
            for _ in range(2 * workers):
                feed()
            while pending:
                check()
                block = pending.popleft().result()
                feed()
                write(block)
                done += block.shape[1]
                tick(done / total)
        except BaseException:
            for f in pending:
                f.cancel()
            raise


def _master_disk_bytes(frames: int, channels: int) -> int:
    """Preflight estimate for scratch, source and in-progress output files.

    Two float32-sized output files cover the encoder source and destination
    (also a conservative allowance for internal WAV/FLAC). Reserve 64 MiB for
    headers, compression/allocation overhead and small concurrent writes. This
    is not a reservation: a later ENOSPC still rolls the export back.
    """
    return (programme.master_scratch_bytes(frames)
            + frames * channels * 4 * 3 + 64 * 1024**2)


def _mastered(job: _Job, sink, channels: int, render, target_lufs: float, workers: int,
              cancel: threading.Event | None, tick: Callable[[float], None],
              target: Path, scratch: list[Path]) -> dict:
    """Spool the rendered mix to disk, then master it with one global decision.

    The raw spool is interleaved float32. Reads allocate only the requested
    block: a full-duration memory mapping can keep touched pages in RSS even
    when the processing itself uses bounded windows. speechmix owns its private
    analysis scratch; this function owns and closes the rendered source on every
    outcome, before the outer export removes its partial output.
    """
    total, rate = job.frames, job.rate
    keep = target.with_name(target.name + ".master.partial")
    def check() -> None:
        try:
            priority.checkpoint(cancel)
        except priority.CancelledError:
            raise _Cancel from None
        if cancel is not None and cancel.is_set():
            raise _Cancel

    check()
    needed = _master_disk_bytes(total, channels)
    if shutil.disk_usage(target.parent).free < needed:
        raise OSError(errno.ENOSPC,
                      f"mastering needs about {needed:,} bytes of free disk space")
    scratch.append(keep)
    try:
        with keep.open("w+b") as audio:
            def store_block(block: np.ndarray) -> None:
                check()
                np.ascontiguousarray(block.T, dtype=np.float32).tofile(audio)

            _pump(total, rate, render, store_block, workers, cancel,
                  lambda f: tick(0.6 * f))
            audio.flush()
            check()

            def read(start: int, stop: int) -> np.ndarray:
                check()
                audio.seek(start * channels * np.dtype(np.float32).itemsize)
                block = np.fromfile(audio, dtype=np.float32,
                                    count=(stop - start) * channels)
                if block.size != (stop - start) * channels:
                    raise OSError("incomplete mastering source")
                return block.reshape(-1, channels).T

            def write(block: np.ndarray) -> None:
                check()
                sink.write(block.astype(np.float32))

            result = programme.master_stream(
                read, write, total, channels, rate, target_lufs,
                check=check, scratch_dir=target.parent,
                progress=lambda f: tick(0.6 + 0.4 * f))
            check()
            tick(1.0)
    finally:
        keep.unlink(missing_ok=True)
        scratch.remove(keep)
    return {"boost_db": result.boost_db, "lufs": result.lufs, "cost_lu": result.cost_lu,
            "reached": bool(result.reached)}


def _run_ffmpeg(cmd: list[str], cancel: threading.Event | None, seconds: float) -> None:
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,  # noqa: S603
                                stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        raise _fail("error.export.no_ffmpeg") from None
    deadline = time.monotonic() + 120 + 2 * seconds
    while True:
        try:
            _, err = proc.communicate(timeout=0.2)
            break
        except subprocess.TimeoutExpired:
            if (cancel is not None and cancel.is_set()) or time.monotonic() > deadline:
                proc.kill()
                proc.communicate()
                if cancel is not None and cancel.is_set():
                    raise _Cancel from None
                raise _fail("error.export.encoder_failed",
                            details="timeout") from None
    if proc.returncode:
        raise _fail("error.export.encoder_failed", details=(err or "").strip()[-300:])


def _produce(job: _Job, target: Path, channels: int,
             render: Callable[[int, int], np.ndarray], *, tags: _Tags,
             master_lufs: float | None, workers: int, cancel: threading.Event | None,
             tick: Callable[[float], None], scratch: list[Path]) -> dict | None:
    """Render ``job.frames`` frames through ``render`` into the file ``target``,
    via ``<target>.partial``. Returns the ``MasterResult`` as a dict if mastered."""
    s, rate, total = job.settings, job.rate, job.frames
    partial = target.with_name(target.name + ".partial")
    scratch.append(partial)
    fade = min(round(FADE_SECONDS * rate), total // 2) if job.ranged else 0

    def faded(first: int, count: int) -> np.ndarray:
        block = render(first, count)
        gain = _edge_gain(first, count, total, fade) if fade else None
        return block if gain is None else (block * gain).astype(np.float32)

    fmt = _format(job)
    encoded = not fmt.internal  # ffmpeg encodes it from a float WAV
    wav_bytes = total * channels * (4 if encoded else s["bit_depth"] // 8)
    if (encoded or s["format"] == "wav") and wav_bytes > MAX_WAV_BYTES:
        raise _fail("error.export.too_big")
    if encoded:
        source = target.with_name(target.name + ".float.partial")
        scratch.append(source)
        depth = 32
    else:
        source, depth = partial, s["bit_depth"]
    master_result = None
    if s["format"] == "flac":
        sink: _WavWriter | _FlacWriter = _FlacWriter(partial, rate, channels, depth, tags)
    else:
        sink = _WavWriter(source, rate, channels, depth, job.first, tags.comment)
    try:
        if master_lufs is not None:
            master_result = _mastered(job, sink, channels, faded, master_lufs, workers,
                                      cancel, tick, target, scratch)
        else:
            _pump(total, rate, faded, sink.write, workers, cancel, tick)
    except BaseException:
        sink.close(complete=False)
        raise
    sink.close()
    if encoded:
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(source),
               *fmt.codec_args(s["bit_depth"], s.get("mp3_kbps"), channels),
               "-metadata", f"title={tags.title}", "-metadata", f"album={tags.album}",
               "-metadata", f"comment={tags.comment}", str(partial)]
        _run_ffmpeg(cmd, cancel, total / rate)
        source.unlink(missing_ok=True)
    os.replace(partial, target)
    scratch.remove(partial)
    return master_result


def _track_channels(project: Project, track: Track) -> int:
    if track.mono:
        return 1
    widths = [project.media_item(c.media).channels for c in track.clips]
    return max(widths, default=1)


def _provenance(job: _Job, n: int) -> _Tags:
    comment = (f"v{n} | edit {job.edit} | project {job.project_name} | "
               f"kuulas {kuulas_version()} | step {job.head}")
    span = f" {_stamp(job.settings['range'][0], job.rate)}\N{EN DASH}" \
           f"{_stamp(job.settings['range'][1], job.rate)}" if job.ranged else ""
    return _Tags(title=f"{job.edit}{span}", album=job.project_name, comment=comment)


# -- the entry point -------------------------------------------------------------


def check(session, args: dict) -> None:
    """Raise now what ``run`` would raise for bad settings or a read-only project,
    so a background job is not queued to fail at once. (An empty edit is still
    reported by the job.)"""
    kind = args.get("kind", "mix")
    with session.lock:
        h = session.history
        h._check_writable()
        settings = _settings(
            kind, h.meta_json("export", {}).get("settings", {}).get(kind), args)
        _check_tracks(h.state, settings)


def run(session, args: dict, progress: Progress | None = None,
        cancel: threading.Event | None = None, workers: int | None = None,
        *, file_name: str | None = None) -> dict:
    """Export; see the module docstring. ``args`` carries ``kind`` (default
    ``mix``) and any settings to change; the rest come from the last export of
    that kind. ``file_name`` (a whole file name, extension included) is for the
    region batch: the file gets exactly that name, and the export is not
    versioned, remembered or checkpointed (the batch does that once). Returns
    ``{"kind", "path", "paths", "version", "skipped", "unchanged_since",
    "master", "message"}``. Raises ``ExportError``.
    """
    job = _snapshot(session, args.get("kind", "mix"), args)
    workers = workers or min(8, os.cpu_count() or 1)
    if file_name is not None:
        job.settings["template"] = (
            Path(file_name).stem.replace("{", "{{").replace("}", "}}") + ".{ext}")

    def say(fraction: float, message: str = "") -> None:
        if progress is not None:
            progress(min(1.0, max(0.0, fraction)), message)

    folder = Path(job.settings["folder"])
    series = _name(job, "#")
    with session.lock:
        runs = session.history.meta_json("export", {}).get("runs", {})
    last = None if file_name is not None else runs.get(f"{job.kind}|{series}")
    reuse = bool(last and last["digest"] == job.digest)
    if reuse:
        old = folder / _name(job, last["n"])
        if old.exists():
            message = t("export.unchanged", n=last["n"], path=str(old))
            if job.kind != "tracks" and job.settings["latest"]:
                _latest(job, folder, old)
            with session.lock:
                h = session.history
                saved = h.meta_json("export", {})
                saved.setdefault("settings", {})[job.kind] = {
                    k: v for k, v in job.settings.items()
                    if k not in NOT_REMEMBERED and k != "folder"
                }
                saved["folder"] = job.settings["folder"]
                h.set_meta_json("export", saved)
            say(1.0, message)
            return {"kind": job.kind, "path": str(old), "paths": _listing(old),
                    "version": last["n"], "skipped": True, "unchanged_since": last["n"],
                    "master": None, "message": message, "settings": job.settings,
                    "placeholders_skipped": job.placeholders, **_counts(job)}
        n = last["n"]  # the file is gone: make it again under the same number
    else:
        n = (last["n"] + 1) if last else 1
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise _fail("error.export.cannot_write", path=str(folder), error=str(e)) from e
    while file_name is None and not reuse and (folder / _name(job, n)).exists():
        n += 1  # never overwrite a file we did not make
    target = folder / _name(job, n)

    scratch: list[Path] = []
    master_result = None
    try:
        if job.kind == "tracks":
            paths = _tracks(job, target, n, workers, cancel, say, scratch)
        else:
            master_result = _single(job, target, n, workers, cancel, say, scratch)
            paths = [target]
        if job.kind != "tracks" and job.settings["latest"]:
            _latest(job, folder, target)
    except _Cancel:
        _clean(scratch)
        raise _fail("error.export.cancelled") from None
    except OSError as e:
        _clean(scratch)
        raise _fail("error.export.cannot_write", path=str(folder), error=str(e)) from e
    except BaseException:
        _clean(scratch)
        raise
    if file_name is not None:
        say(1.0, "")
        return {"kind": job.kind, "path": str(target), "paths": [str(target)],
                "version": n, "skipped": False, "unchanged_since": None,
                "master": master_result, "message": "", "settings": job.settings,
                "placeholders_skipped": job.placeholders, **_counts(job)}
    return _finish(session, job, n, series, target, paths, master_result, say)


def _clean(scratch: list[Path]) -> None:
    for p in scratch:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            with contextlib.suppress(OSError):
                p.unlink(missing_ok=True)


def _listing(path: Path) -> list[str]:
    if path.is_dir():
        return [str(p) for p in sorted(path.iterdir()) if p.suffix != ".json"]
    return [str(path)]


def _single(job: _Job, target: Path, n: int, workers: int,
            cancel: threading.Event | None, say: Progress, scratch: list[Path]):
    lufs = job.settings.get("master_lufs")
    if lufs is not None and job.frames / job.rate > MAX_MASTER_SECONDS:
        raise _fail("error.export.too_long_to_master",
                    hours=MAX_MASTER_SECONDS // 3600)
    if lufs is not None and not master_fits(job.frames, 2):
        raise _fail("error.export.master_memory",
                    minutes=master_minutes_that_fit(2, job.rate))

    def render(first: int, count: int) -> np.ndarray:
        return mixer.mix(job.project, job.store, job.first + first, count)

    return _produce(job, target, 2, render, tags=_provenance(job, n),
                    master_lufs=lufs, workers=workers, cancel=cancel,
                    tick=lambda f: say(0.95 * f), scratch=scratch)


def _bus_db(p, track) -> float:
    """The gain of the track's bus, dB (0 without a bus)."""
    try:
        return p.bus(track.bus).gain_db if track.bus else 0.0
    except KeyError:
        return 0.0


def _tracks(job: _Job, target: Path, n: int, workers: int,
            cancel: threading.Event | None, say: Progress,
            scratch: list[Path]) -> list[Path]:
    work = target.with_name(target.name + ".partial")
    scratch.append(work)
    work.mkdir()
    p, s = job.project, job.settings
    as_heard = s["processing"] == "as_heard"
    # The balance the user set with track gain (effects against music, one microphone
    # against another) goes into the stems: the automixer keeps the balance between the
    # music tracks and does not equalise the speakers against each other.
    track_gain = bool(s.get("for_automixer"))
    listing, paths, used = [], [], set()
    ext = _format(job).ext
    tracks = _exported(p, s)
    for i, track in enumerate(tracks):
        channels = _track_channels(p, track)
        if s.get("for_automixer") and track.kind == "music":
            channels = 2  # the automixer refuses mono music
        stem = _safe(track.name)
        if track.kind == "music" and not any(w in stem.upper() for w in MUSIC_WORDS):
            stem += " MUSIC"  # the automixer reads the role from the file name
        base = _safe(f"{_title(job)} \N{EN DASH} {stem}")
        while base in used:
            base += " (2)"
        used.add(base)
        audible = _audible(p, track)
        bus_db = _bus_db(p, track)
        track_automation = (bool(s.get("for_automixer")) and track.kind == "music"
                            and track.duck is not False and bool(track.automation))

        def render(first: int, count: int, track=track, channels=channels,
                   audible=audible, bus_db=bus_db,
                   track_automation=track_automation) -> np.ndarray:
            if not audible:
                return np.zeros((channels, count), dtype=np.float32)
            return mixer.track_stem(track, job.store, job.first + first, count,
                                    channels, as_heard=as_heard, rate=job.rate,
                                    track_gain=track_gain, bus_db=bus_db,
                                    track_automation=track_automation)

        done = work / f"{base}.{ext}"
        _produce(job, done, channels, render, tags=_provenance(job, n),
                 master_lufs=None, workers=workers, cancel=cancel,
                 tick=lambda f, i=i: say(0.95 * (i + f) / len(tracks)), scratch=[])
        paths.append(done)
        listing.append({"id": track.id, "name": track.name, "kind": track.kind,
                        "speaker": track.speaker, "channels": channels, "file": done.name,
                        "audible": audible, "gain_db": track.gain_db, "pan": track.pan})
        if audible:  # an inaudible stem is all silence: audible=false says it
            span = (job.first, job.frames)
            for key, found in (
                    ("muted_frames", stem_ranges.muted_ranges(track, *span)),
                    ("gate_frames", stem_ranges.gate_ranges(track, *span))):
                if found:
                    listing[-1][key] = found
    if s.get("list_file"):
        (work / "tracks.json").write_text(json.dumps({
            "edit": job.edit, "project": job.project_name, "title": _title(job),
            # the automixer's folder route reads "version" as the manifest version (1)
            "version": 1 if s.get("for_automixer") else n,
            **({"export_version": n} if s.get("for_automixer") else {}), "rate": job.rate,
            # The automixer's folder route requires 0: its stems are range-relative.
            # (Kuulas keeps a range's real start in its own result, never here.)
            "start_frame": 0 if s.get("for_automixer") else job.first,
            "frames": job.frames, "processing": s["processing"],
            "format": ext, "bit_depth": s["bit_depth"], "tracks": listing},
            indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(work, target)
    scratch.remove(work)
    return [target / x.name for x in paths]


def _latest(job: _Job, folder: Path, target: Path) -> None:
    """Keep ``{title} latest.{ext}`` equal to the newest version, for a fixed
    upload path. Copied through a ``.partial`` and renamed, so it is never half."""
    name = f"{_safe(_title(job))} latest.{job.settings['format']}"
    if name == target.name:
        return
    keep = folder / name
    partial = keep.with_name(keep.name + ".partial")
    try:
        shutil.copyfile(target, partial)
        os.replace(partial, keep)
    finally:
        partial.unlink(missing_ok=True)


def _finish(session, job: _Job, n: int, series: str, target: Path, paths: list[Path],
            master: dict | None, say: Progress) -> dict:
    """Record the export: the settings and run in the project, then a checkpoint
    of the step that was rendered (which may no longer be the head)."""
    what = _describe(job)
    with session.lock:
        h = session.history
        saved = h.meta_json("export", {})
        remembered = {k: v for k, v in job.settings.items()
                      if k not in NOT_REMEMBERED and k != "folder"}
        saved.setdefault("settings", {})[job.kind] = remembered
        saved["folder"] = job.settings["folder"]
        saved.setdefault("runs", {})[f"{job.kind}|{series}"] = {
            "n": n, "digest": job.digest, "name": target.name}
        h.set_meta_json("export", saved)
        h.checkpoint(t("history.export", n=n, what=what), "export", node=job.head)
    message = t("export.done", what=what, path=str(target))
    say(1.0, message)
    return {"kind": job.kind, "path": str(target), "paths": [str(p) for p in paths],
            "version": n, "skipped": False, "unchanged_since": None, "master": master,
            "message": message, "settings": job.settings,
            "placeholders_skipped": job.placeholders, **_counts(job)}


def _counts(job: _Job) -> dict:
    """How many tracks a track export covers and which came out silent (a mix
    reports only the silent ones)."""
    if job.kind != "tracks":
        return {"silent": list(job.silent)}
    return {"track_count": len(_exported(job.project, job.settings)),
            "silent": list(job.silent),
            # What the stems were rendered from (``audio_key``): a render made of them
            # matches the edit while the edit still has this key.
            "audio_key": audio_key(job.project), "first": job.first,
            "frames": job.frames}


def last_settings(session, kind: str) -> dict | None:
    """The settings the last export of ``kind`` used in this project, if any."""
    with session.lock:
        return session.history.meta_json("export", {}).get("settings", {}).get(kind)


# -- regions (WP19h) -----------------------------------------------------------

# Leads with the project (and the edit, unless it is the main one): owner, 2026-10-20.
REGION_TEMPLATE = "{title} - {n:02d} {name}"


def plan_regions(session, args: dict) -> tuple[list[tuple[int, int, str]], dict]:
    """Each region as ``(first, end, file name)`` and the settings to render
    them with, checked now so a bad request fails before a job is queued.

    A region is clamped to the programme; one that starts past its end has
    nothing to render and is left out. File names come from the region names
    (``region_names.region_filenames``) and avoid what is already in the
    folder, so a second run never overwrites the first.
    """
    template = args.get("name_template") or REGION_TEMPLATE
    with session.lock:
        project = session.history.state
        saved = session.history.meta_json("export", {})
        folder = (args.get("folder") or saved.get("folder")
                  or str(session.package.path.parent
                         / f"{session.package.path.stem} exports"))
        regions = [m for m in project.markers if m.kind == "region"]
        edit_name = next((e["name"] for e in session.history.edits()
                          if e["id"] == session.history.edit), session.history.edit)
        names_for = {"project": _safe(session.package.path.stem),
                     "title": _safe(export_names.title(
                         session.package.path.stem, session.history.edit, edit_name))}
        total = project.length
        rate = project.rate
    spans = [(m, m.start, min(m.end, total)) for m in regions if m.start < total]
    if not spans:
        raise KuulasError("error.regions.none")
    folder_path = Path(folder)
    existing = ([p.name for p in folder_path.iterdir()]
                if folder_path.is_dir() else [])
    fmt = args.get("format") or export_formats.DEFAULT
    chosen = export_formats.get(fmt)
    if chosen is None:
        raise _fail("error.export.bad_format", format=fmt,
                    available=", ".join(f.id for f in export_formats.available_formats()))
    names = region_filenames([(m.name, m.start / rate) for m, _a, _b in spans],
                             template, chosen.ext, existing, names_for)
    settings = {"folder": str(folder), "format": fmt}
    for key in ("bit_depth", "mp3_kbps", "master_lufs"):
        if args.get(key) is not None:
            settings[key] = args[key]
    plan = [(a, b, name) for (_m, a, b), name in zip(spans, names, strict=True)]
    return plan, settings


def run_regions(session, plan: list[tuple[int, int, str]], settings: dict,
                progress: Progress | None = None,
                cancel: threading.Event | None = None) -> dict:
    """Render every planned region to its own file with the selection export.
    One call, one progress bar: ``progress`` sees 0..1 over all of them."""
    paths: list[str] = []
    with session.lock:
        head = session.history.head
    count = len(plan)
    for i, (first, end, name) in enumerate(plan):
        if cancel is not None and cancel.is_set():
            raise _fail("error.export.cancelled")

        def say(fraction: float, message: str = "", i=i) -> None:
            if progress is not None:
                progress((i + fraction) / count, message)

        result = run(session, {**settings, "kind": "selection", "range": [first, end]},
                     say, cancel, file_name=name)
        paths.append(result["path"])
    with session.lock:
        session.history.checkpoint(t("history.export_regions", count=count),
                                   "export", node=head)
    return {"paths": paths, "count": count, "folder": settings["folder"]}
