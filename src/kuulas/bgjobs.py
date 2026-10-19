"""Transcription as a detached background job (WP79): the job files.

A job is a few files in ``<project>.kuulas/jobs/``, so it lives with the project
and outlives the editor:

* ``<id>.json``: what to do (written once, before anything starts): backend,
  audio paths as resolved, model, language, the Colab settings as they were,
  the host that owns it and the transcript revision each media had at submit.
* ``<id>.status.json``: the worker's own progress, replaced atomically.
* ``<id>.<media>.words.json``: the result per media, in the Colab contract's
  shape (``colab_transcribe.read_words_json`` reads it strictly). The worker
  never opens the project database; the editor ingests (``Session``).

The editor also writes ``<id>.cancel`` (a request the worker polls; a file and
not a signal, so it works the same for every launcher and never needs a pid)
and ``<id>.ingested.json`` (which media were added, which found a newer
transcript). Nothing here imports the editor session; the worker imports this
module and ``colab_transcribe`` only.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .clock import FLICKS
from .messages import KuulasError, t
from .package import _hostname, _pid_alive, write_json_atomic

log = logging.getLogger("kuulas.bgjobs")

JOBS_DIR = "jobs"
VERSION = 1
#: A queued job whose worker never wrote its pid is called interrupted after this
#: long (the launch itself failed or the machine went down at once).
QUEUED_GRACE_S = 60
_SAFE = re.compile(r"[A-Za-z0-9._-]+")
FINISHED = frozenset({"completed", "failed", "cancelled", "interrupted"})


class BackgroundJobError(KuulasError, RuntimeError):
    """A background job could not be started or changed (a message key)."""


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(text: object) -> datetime | None:
    try:
        return datetime.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def jobs_dir(folder: Path | str) -> Path:
    return Path(folder) / JOBS_DIR


def job_file(folder: Path | str, job_id: str) -> Path:
    return jobs_dir(folder) / f"{job_id}.json"


def status_file(folder: Path | str, job_id: str) -> Path:
    return jobs_dir(folder) / f"{job_id}.status.json"


def cancel_file(folder: Path | str, job_id: str) -> Path:
    return jobs_dir(folder) / f"{job_id}.cancel"


def marker_file(folder: Path | str, job_id: str) -> Path:
    return jobs_dir(folder) / f"{job_id}.ingested.json"


def result_file(folder: Path | str, job_id: str, media_id: str) -> Path:
    if not _SAFE.fullmatch(media_id):
        raise BackgroundJobError("error.server.bad_request", detail="media id")
    return jobs_dir(folder) / f"{job_id}.{media_id}.words.json"


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def create_job(folder: Path | str, *, backend: str, items: list[dict],
               previous: dict, names: list[str], model: str | None,
               language: str | None, settings: dict | None,
               cpu_threads: int | None = None) -> str:
    """Write the job file and an initial ``queued`` status; returns the id. Nothing
    runs yet: ``launch_worker`` does that."""
    job_id = secrets.token_hex(8)
    jobs_dir(folder).mkdir(parents=True, exist_ok=True)
    write_json_atomic(job_file(folder, job_id), {
        "version": VERSION, "id": job_id, "backend": backend,
        "items": [{"id": i["id"], "name": i["name"], "path": str(i["path"])}
                  for i in items],
        "names": names, "model": model, "language": language,
        "settings": settings, "cpu_threads": cpu_threads,
        "previous": previous, "host": _hostname(), "created": now_iso()})
    write_json_atomic(status_file(folder, job_id), {
        "state": "queued", "progress": 0.0, "message": "", "indeterminate": True,
        "log": [], "pid": None, "host": _hostname(), "finished": None})
    return job_id


def job_ids(folder: Path | str) -> list[str]:
    """The ids of the jobs in the project, oldest first."""
    try:
        files = list(jobs_dir(folder).glob("*.json"))
    except OSError:
        return []
    found = []
    for path in files:
        name = path.name
        if name.endswith((".status.json", ".ingested.json", ".words.json")):
            continue
        data = read_json(path)
        if data and data.get("id") == name[:-5]:
            found.append((str(data.get("created", "")), name[:-5]))
    return [job_id for _, job_id in sorted(found)]


def _error_of(error: object) -> dict | None:
    if not isinstance(error, dict) or not isinstance(error.get("key"), str):
        return None
    params = error.get("params") if isinstance(error.get("params"), dict) else {}
    try:
        text = str(t(error["key"], **params))
    except Exception:  # noqa: BLE001 - a key from a newer version: show it as is
        text = str(error.get("text") or error["key"])
    return {"key": error["key"], "params": params, "text": text}


def describe(folder: Path | str, job_id: str) -> dict | None:
    """The job as ``/api/jobs`` lists it, or None when its job file is gone.
    ``state`` is the worker's, except that a ``queued``/``running`` job on this
    host whose worker is gone is ``interrupted`` (killed, logout, reboot);
    ``foreign`` marks a job another computer owns (it is shown, not run)."""
    job = read_json(job_file(folder, job_id))
    if job is None:
        return None
    status = read_json(status_file(folder, job_id)) or {}
    mine = job.get("host") == _hostname()
    state = status.get("state") if isinstance(status.get("state"), str) else "queued"
    error = _error_of(status.get("error"))
    if state in {"queued", "running"} and mine:
        pid = status.get("pid")
        created = _parse(job.get("created"))
        old = created is not None and (
            datetime.now(UTC) - created).total_seconds() > QUEUED_GRACE_S
        if (isinstance(pid, int) and not _pid_alive(pid)) or (pid is None and old):
            state = "interrupted"
            error = _error_of({"key": "error.transcribe.interrupted"})
    marker = read_json(marker_file(folder, job_id)) or {}
    outcome = marker.get("media") if isinstance(marker.get("media"), dict) else {}
    if state == "completed" and len(outcome) >= len(job.get("items", [])) > 0 \
            and any(v != "added" for v in outcome.values()):
        # Finished, but some results were not stored (a newer transcript, a bad file).
        state = "failed"
        error = _error_of({"key": "error.transcribe.changed"})
    names = ", ".join(job.get("names") or [])
    key = "job.transcribe_colab" if job.get("backend") == "colab" else "job.transcribe"
    progress = status.get("progress")
    return {"id": job_id, "kind": "transcribe", "title": str(t(key, names=names,
                                                               name=names)),
            "backend": job.get("backend"), "state": state,
            "progress": float(progress) if isinstance(progress, int | float) else 0.0,
            "message": str(status.get("message") or ""),
            "indeterminate": bool(status.get("indeterminate")),
            "remaining_seconds": None, "error": error, "foreign": not mine,
            "host": job.get("host"), "background": True}


def request_cancel(folder: Path | str, job_id: str) -> None:
    """Ask the worker to stop (it polls for this file). A job nobody is running
    is marked cancelled at once. Refused for another computer's job."""
    info = describe(folder, job_id)
    if info is None:
        return
    if info["foreign"] and info["state"] in {"queued", "running"}:
        raise BackgroundJobError("error.transcribe.foreign_host", host=info["host"])
    if info["state"] == "interrupted":
        status = read_json(status_file(folder, job_id)) or {}
        write_json_atomic(status_file(folder, job_id), {
            **status, "state": "cancelled", "finished": now_iso(), "error": None})
        return
    if info["state"] in {"queued", "running"}:
        cancel_file(folder, job_id).write_text("cancel\n", encoding="utf-8")


def remove_files(folder: Path | str, job_id: str) -> None:
    """Delete every file of the job (dismissing it, or after its results are in)."""
    for path in jobs_dir(folder).glob(f"{job_id}.*"):
        with contextlib.suppress(OSError):
            path.unlink()


def launch_worker(path: Path | str) -> None:
    """Start ``kuulas.transcribe_worker`` on the job file, detached in its own
    session, so it keeps going when the editor window, the app or the project is
    closed. Tests replace this function; nothing waits for the process."""
    subprocess.Popen(  # noqa: S603 - our own module, fixed argv
        [sys.executable, "-m", "kuulas.transcribe_worker", "run", str(path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True, env=os.environ.copy())


def words_to_file(words: list[dict], *, timing: str, language: str,
                  rejected: int = 0) -> dict[str, Any]:
    """The Colab contract's shape (seconds) from stored words (flicks)."""
    doc: dict[str, Any] = {
        "version": 1, "timing": timing, "language": language,
        "words": [{"w": w["w"], "s": w["s"] / FLICKS, "e": w["e"] / FLICKS}
                  for w in words]}
    if rejected:
        doc["rejected"] = rejected
    return doc
