"""The warm Orukeet engine for live takes: one model load per take, many chunks.

Reuses the Orukeet installation the user's cold transcription path already has
(the receipt colab-transcribe's orukeet backend writes: ``ORUKEET_INSTALLATION``
or ``~/.cache/orukeet/installation.json``, naming the GGUF model, the native
runtime and the device). Nothing is downloaded and no second model is
installed: without a valid receipt there is no live transcription, and the
take records exactly as before.
"""

from __future__ import annotations

import array
import json
import logging
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

log = logging.getLogger("kuulas.live_engine")

RECEIPT = Path.home() / ".cache" / "orukeet" / "installation.json"
WHEEL = ("https://github.com/Oruk-AI/orukeet/releases/download/v0.1.1/"
         "orukeet-0.1.1-py3-none-any.whl")
WORKER = Path(__file__).with_name("orukeet_live_worker.py")


def receipt_path() -> Path:
    return Path(os.environ.get("ORUKEET_INSTALLATION", RECEIPT)).expanduser()


def read_receipt(path: Path | None = None) -> dict | None:
    """The installation's model/runtime/device, all verified to exist, else None."""
    path = path or receipt_path()
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        model, runtime = Path(config["model"]), Path(config["runtime"])
        device = str(config["device"])
        if model.is_file() and runtime.is_dir() and device:
            return {"model": str(model), "runtime": str(runtime),
                    "device": device}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def worker_command(python: str | None = None) -> list[str]:
    """The worker's command: same dependency-resolution pattern as transcribe.py.

    uv resolves and caches the pinned orukeet wheel (and its numpy/av); the
    model and runtime come from the existing installation receipt, never from
    a new download.
    """
    return [python or "uv", "run", "--no-project", "--with", WHEEL,
            "--with", "av", "python", "-u", str(WORKER)] if python is None else [
            python, "-u", str(WORKER)]


class LiveEngineProcess:
    """One serialized request stream to the worker; adapted from the SDK's
    SpeechProcess (orukeet.process) with the same timeout/cancel semantics."""

    def __init__(self, command: list[str] | None = None):
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._serial = 0
        self._closed = False
        self._replies: queue.Queue = queue.Queue()
        self._errors: deque = deque(maxlen=25)
        environment = os.environ.copy()
        environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                           PYTHONUTF8="1")
        self.process = subprocess.Popen(
            command or worker_command(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", bufsize=1, env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._readers = [
            threading.Thread(target=self._read, daemon=True,
                             name="live-engine-results"),
            threading.Thread(target=self._read_errors, daemon=True,
                             name="live-engine-errors"),
        ]
        for reader in self._readers:
            reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self._replies.put(json.loads(line))
                except ValueError:
                    self._errors.append(line.rstrip())
        finally:
            self._replies.put(None)

    def _read_errors(self):
        for line in self.process.stderr:
            self._errors.append(line.rstrip())

    def request(self, op: str, *, timeout=180., **payload) -> dict:
        with self._lock:
            with self._state_lock:
                if self._closed:
                    raise RuntimeError("Live speech engine is closed")
                self._serial += 1
                serial = self._serial
                try:
                    self.process.stdin.write(
                        json.dumps(dict(id=serial, op=op, **payload)) + "\n")
                    self.process.stdin.flush()
                except (BrokenPipeError, OSError, ValueError) as exc:
                    raise RuntimeError(
                        "Live speech worker stopped; the lane reloads next take"
                    ) from exc
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.close()
                    raise RuntimeError("Live speech engine timed out and was stopped")
                try:
                    response = self._replies.get(timeout=min(.2, remaining))
                except queue.Empty:
                    if self._closed:
                        raise RuntimeError("Live speech engine is closed")
                    continue
                if self._closed:
                    raise RuntimeError("Live speech engine is closed")
                if response is None:
                    raise RuntimeError(
                        "Live speech worker stopped: "
                        + " ".join(self._errors)[-1600:])
                if response.get("id") != serial:
                    continue
                if response.get("error"):
                    raise RuntimeError(response["error"])
                return response["result"]

    def close(self):
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            if self.process.poll() is None:
                self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()


def warm_engine_factory(receipt: dict | None = None, *,
                        command: list[str] | None = None,
                        spawn=None, timeout=300.):
    """The sidecar's engine_factory: load once per take, transcribe many chunks.

    The returned ``engine(audio, rate)`` takes mono float samples at the take's
    rate and returns native word dicts (seconds from the chunk's start), the
    shape LiveTranscriber stores. Raises when the model cannot load - the
    sidecar counts that toward the lane's failure budget, never the take's.
    """
    receipt = receipt if receipt is not None else read_receipt()
    if receipt is None:
        raise RuntimeError("error.orukeet.no_installation")
    make = spawn or (lambda: LiveEngineProcess(command))
    process = make()
    process.request("load", model_path=receipt["model"],
                    runtime=receipt["runtime"], device=receipt["device"],
                    timeout=timeout)

    def engine(audio, rate):
        samples = array.array("f", (float(x) for x in audio))
        with tempfile.NamedTemporaryFile(
                prefix="kuulas-live-", suffix=".f32", delete=False) as tmp:
            samples.tofile(tmp)
            path = tmp.name
        try:
            result = process.request("transcribe", audio_path=path,
                                     rate=int(rate), timeout=timeout)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        return result["words"]

    engine.close = process.close  # the sidecar closes the worker with the take
    return engine


def factory_or_none(receipt: dict | None = None, **kwargs):
    """The RecordSession wiring helper: a factory, or None to record without one."""
    receipt = receipt if receipt is not None else read_receipt()
    if receipt is None:
        return None
    return lambda: warm_engine_factory(receipt, **kwargs)
