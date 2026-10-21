"""Listen to the rendered mix inside Kuulas (owner, 2026-10-21: "Once we've rendered the
Automix file, could we listen to it inside Kuulas? ... Because then you could hear all
the effects. If you change anything in the timeline, you cannot listen to the preview
anymore.").

After an automix run (the whole edit, or only the In/Out range) the project remembers
the file in ``mix_done.render`` (docs/FORMAT.md). While the edit still sounds as it did
when the stems were taken (``export.audio_key`` unchanged) and the file is there with the
size it had, the engine can play the file instead of the tracks: a stand-in project of
ONE clip holding the file at its place on the timeline (0 for a whole render, the range's
start for a range), so seek, loop, speed and Space work as for the edit. The project
itself is never changed, nothing goes into history, and the file is never deleted
(ground rule 17); a stale record is kept so the UI can say there is an older render.

The file is read where it lies, through ``FileSource`` (libsndfile, any rate: resampled
to the project rate block by block with soxr), never imported into the media store: it
is not material of the edit.
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import soxr

from . import export
from .messages import KuulasError
from .model import Clip, Media, Project, Track

log = logging.getLogger("kuulas.render_listen")

#: Source frames read on each side of a resampled block, so the filter's start-up at the
#: block's edges falls outside what is used (soxr HQ settles within a few hundred).
RESAMPLE_PAD = 1024
TRACK_ID = "render-listen"
CLIP_ID = "render-listen-clip"


class RenderListenError(KuulasError, RuntimeError):
    """No render to listen to, or it no longer matches the edit (a message key)."""


# -- the record ------------------------------------------------------------------------


def entry(result: dict, at: str) -> dict | None:
    """The ``mix_done.render`` entry for an automix run's ``result`` (``path``, ``name``,
    ``range``, ``edit_key``, ``frames``, ``rate``), stamped ``set_at`` (ISO, with its
    zone) and with the file's size now. None when the result lacks what listening needs
    or the file cannot be looked at."""
    path, key = result.get("path"), result.get("edit_key")
    if not isinstance(path, str) or not isinstance(key, str):
        return None
    try:
        size = Path(path).stat().st_size
    except OSError:
        return None
    rng = result.get("range")
    name = result.get("name") or Path(path).name
    return {"path": str(Path(path).absolute()), "name": name,
            "range": list(rng) if rng else None, "edit_key": key, "set_at": at,
            "frames": result.get("frames"), "rate": result.get("rate"), "size": size}


def _record(p: Project) -> dict | None:
    found = (p.mix_done or {}).get("render")
    if not isinstance(found, dict) or not isinstance(found.get("path"), str):
        return None
    return found


def _reason(p: Project, found: dict) -> str | None:
    """Why the render does not match the edit now (None: it does). ``missing``: no
    file; ``changed``: another size than when it was rendered; ``edited``: the edit
    sounds different (``export.audio_key``)."""
    try:
        size = Path(found["path"]).stat().st_size
    except OSError:
        return "missing"
    if size != found.get("size"):
        return "changed"
    if found.get("edit_key") != export.audio_key(p):
        return "edited"
    return None


def render_current(p: Project) -> dict | None:
    """The render record while it still matches the edit, else None.

    It stops matching when anything that changes the sound changes
    (``export.audio_key``): clips (added, removed, moved, trimmed), their offsets, gains,
    fades, envelopes and mutes, gates, automation, a track's gain, pan, mute or solo,
    a bus's gain, mute or role (it changes the stems), the master gain, the media's
    identities and the rate; or when the file is gone or has another size. The playhead,
    markers, the selection, view settings and names do NOT change it."""
    found = _record(p)
    if found is None or _reason(p, found) is not None:
        return None
    return found


def status(p: Project) -> dict[str, Any]:
    """What the UI draws: ``available`` (a render is remembered), ``current`` (it
    matches the edit), ``missing`` (its file is gone), ``reason`` (why not current:
    ``edited``, ``changed``, ``missing``; None), ``name``, ``range``, ``set_at``."""
    found = _record(p)
    if found is None:
        return {"available": False, "current": False, "missing": False, "name": None,
                "range": None, "set_at": None, "reason": None}
    reason = _reason(p, found)
    return {"available": True, "current": reason is None, "missing": reason == "missing",
            "name": found.get("name"), "range": found.get("range"),
            "set_at": found.get("set_at"), "reason": reason}


# -- reading the file ------------------------------------------------------------------


class FileSource:
    """The rendered file as the engine's store reads media: ``read(media_id, first,
    count)`` -> ``(channels, count)`` float32 at the project ``rate``, zero-padded.

    Read where it lies with libsndfile (24-bit and float WAV, FLAC, any rate). A file at
    another rate is resampled block by block: each block is read with ``RESAMPLE_PAD``
    source frames on each side, resampled with soxr HQ and the middle kept, so the edges
    of blocks do not click. Opening is lazy and a read that fails raises (the engine's
    reader then plays that chunk as silence and says so)."""

    def __init__(self, path: str | Path, rate: int):
        self.path = str(path)
        self.rate = int(rate)
        info = sf.info(self.path)  # unreadable: LibsndfileError (a RuntimeError)
        st = Path(self.path).stat()
        self.file_rate = int(info.samplerate)
        self.file_frames = int(info.frames)
        self.channels = max(1, int(info.channels))
        self.frames = (self.file_frames if self.file_rate == self.rate
                       else round(self.file_frames * self.rate / self.file_rate))
        ident = f"{self.path}|{st.st_size}|{st.st_mtime_ns}".encode()
        self.media_id = "render-" + hashlib.sha256(ident).hexdigest()[:16]
        self._lock = threading.Lock()
        self._file: sf.SoundFile | None = None

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None

    def _read_source(self, lo: int, hi: int) -> np.ndarray:
        """Source frames ``[lo, hi)`` as ``(n, channels)`` float32, zeros outside."""
        out = np.zeros((hi - lo, self.channels), dtype=np.float32)
        a, b = max(0, lo), min(self.file_frames, hi)
        if b <= a:
            return out
        with self._lock:
            if self._file is None:
                self._file = sf.SoundFile(self.path)
            self._file.seek(a)
            data = self._file.read(b - a, dtype="float32", always_2d=True)
        out[a - lo:a - lo + data.shape[0], :data.shape[1]] = data[:, :self.channels]
        return out

    def read(self, media_id: str, first: int, count: int) -> np.ndarray:
        del media_id  # one file: the engine asks by the id it was given
        count = max(0, int(count))
        if self.file_rate == self.rate:
            return np.ascontiguousarray(self._read_source(first, first + count).T)
        ratio = self.file_rate / self.rate
        # The block starts on a source frame that is also a whole output frame (a
        # multiple of file_rate / gcd), so the kept part needs no fractional shift.
        grid = self.file_rate // math.gcd(self.file_rate, self.rate)
        lo = math.floor((first * ratio - RESAMPLE_PAD) / grid) * grid
        hi = math.ceil((first + count) * ratio) + RESAMPLE_PAD
        resampled = soxr.resample(self._read_source(lo, hi), self.file_rate, self.rate,
                                  quality="HQ")
        # Output frame j of the block is at time lo / file_rate + j / rate.
        skip = first - lo * self.rate // self.file_rate
        out = np.zeros((self.channels, count), dtype=np.float32)
        piece = resampled[max(0, skip):max(0, skip) + count]
        out[:, :piece.shape[0]] = piece.T
        return out


def listen_project(rate: int, source: FileSource, offset: int,
                   length: int = 0) -> Project:
    """The stand-in the engine plays: the file as one clip at timeline frame ``offset``
    on one centred track, unity gain, nothing else. Silence outside its span. ``length``
    (the edit's) keeps the programme as long as the edit: the clip runs on past the
    file's end as silence (the reader pads with zeros), so a range render does not end
    the playback, or pull the playhead back, at the range's end."""
    start = max(0, int(offset))
    media = Media(id=source.media_id, name=Path(source.path).name,
                  channels=source.channels, frames=source.frames)
    clip = Clip(id=CLIP_ID, media=source.media_id, start=start, offset=0,
                length=max(source.frames, int(length) - start))
    return Project(rate=rate, media=(media,),
                   tracks=(Track(id=TRACK_ID, name=media.name, clips=(clip,)),))


# -- switching the engine ----------------------------------------------------------------


def start(session, engine) -> dict:
    """Play the remembered render instead of the edit. The record is checked under the
    session lock; the file is opened outside it. Raises ``RenderListenError``:
    ``none`` (no render), ``stale`` (the edit changed since), ``missing`` (the file is
    gone or changed), ``unreadable``. Returns the record."""
    with session.lock:
        project = session.state
        found = _record(project)
        reason = None if found is None else _reason(project, found)
    if found is None:
        raise RenderListenError("error.render_listen.none")
    if reason == "edited":
        raise RenderListenError("error.render_listen.stale")
    if reason is not None:
        raise RenderListenError("error.render_listen.missing", name=found.get("name", ""))
    try:
        source = FileSource(found["path"], project.rate)
    except (OSError, RuntimeError) as e:
        raise RenderListenError("error.render_listen.unreadable",
                                name=found.get("name", ""), error=str(e)) from e
    offset = int((found.get("range") or [0])[0])
    path, key = found["path"], found.get("edit_key")
    engine.set_listen_source(listen_project(project.rate, source, offset, project.length),
                             {source.media_id: source}, keep=keeper(path, key))
    return found


def keeper(path: str, key: str | None) -> Callable[[Project], bool]:
    """The engine's check after every change of the project: listening goes on only
    while the same render is remembered and still matches the edit."""
    def keep(p: Project) -> bool:
        found = render_current(p)
        return (found is not None and found["path"] == path
                and found.get("edit_key") == key)

    return keep


def stop(engine) -> None:
    engine.clear_listen_source()
