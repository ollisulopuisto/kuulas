"""Install and validate the Orukeet SDK runtime used for local transcription."""

from __future__ import annotations

import json
import os
import platform
import threading
from pathlib import Path

from . import colab_transcribe, local_memory
from .automix import run_process
from .jobs import JobCancelledError
from .messages import KuulasError

ORUKEET_WHEEL = (
    "https://github.com/Oruk-AI/orukeet/releases/download/v0.1.1/"
    "orukeet-0.1.1-py3-none-any.whl"
)
ORUKEET_TORCH = "torch==2.8.0"
ORUKEET_TORCHAUDIO = "torchaudio==2.8.0"
SOURCE = "https://github.com/Oruk-AI/orukeet"
_LOCK = threading.Lock()


class ModelError(KuulasError, ValueError):
    """The local SDK setup could not be installed or is no longer usable."""


def installation_file() -> Path:
    override = os.environ.get("ORUKEET_INSTALLATION")
    return Path(override).expanduser() if override else (
        Path.home() / ".cache" / "orukeet" / "installation.json")


def _paths_exist(paths: list[str]) -> bool:
    try:
        checked = [Path(path).expanduser() for path in paths]
        return all(path.is_absolute() and path.exists() for path in checked)
    except (OSError, ValueError):
        return False


def _receipt() -> dict | None:
    try:
        value = json.loads(installation_file().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    paths = [value.get(key) for key in ("model", "runtime")]
    if not all(isinstance(path, str) and path.strip() for path in paths):
        return None
    if not isinstance(value.get("device"), str) or not value["device"].strip():
        return None
    if not _paths_exist(paths):
        return None
    return value


def status() -> dict:
    receipt = installation_file()
    supported = platform.system() == "Darwin" and platform.machine() == "arm64"
    return {"ready": supported and _receipt() is not None,
            "path": str(receipt.parent), "receipt": str(receipt),
            "supported": supported,
            "eligible": local_memory.eligible(),
            "memory_minimum_bytes": local_memory.MINIMUM_BYTES,
            "source": SOURCE}


def install_command() -> list[str]:
    """Build the SDK installer command in the same isolated environment as the CLI."""
    command = colab_transcribe.default_command()
    receipt = installation_file()
    args = ["install", "--device", "auto", "--cache", str(receipt.parent),
            "--output", str(receipt)]
    if command[0] == "uvx":
        return [command[0], "--with", ORUKEET_WHEEL,
                "--with", ORUKEET_TORCH, "--with", ORUKEET_TORCHAUDIO,
                *command[1:-1], "orukeet", *args]
    if command[:2] == ["uv", "run"]:
        return ["uv", "run", "--frozen", "--extra", "orukeet",
                "--with", ORUKEET_TORCH, "--with", ORUKEET_TORCHAUDIO,
                *command[2:-1], "orukeet", *args]
    raise ModelError("error.orukeet.install", error="Unsupported uv command")


class _Cancel:
    def __init__(self, progress):
        self.progress = progress

    def is_set(self) -> bool:
        return bool(getattr(self.progress, "cancelled", False))


def install(progress) -> dict:
    """Run ``orukeet install`` and trust it only after validating its receipt."""
    if not status()["supported"]:
        raise ModelError("error.orukeet.platform")
    if not _LOCK.acquire(blocking=False):
        raise ModelError("error.orukeet.busy")
    try:
        receipt = installation_file()
        receipt.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []

        def on_line(line: str) -> None:
            lines.append(line)
            del lines[:-20]
            progress(0.5, line[-240:] or None, True)

        progress(0.01, None, True)
        code = run_process(install_command(), None, on_line, _Cancel(progress))
        if getattr(progress, "cancelled", False):
            raise JobCancelledError
        if code != 0:
            raise ModelError("error.orukeet.install", error="\n".join(lines))
        if _receipt() is None:
            raise ModelError("error.orukeet.receipt", path=str(receipt))
        progress(1.0)
        return status()
    except OSError as error:
        raise ModelError("error.orukeet.install", error=str(error)) from error
    finally:
        _LOCK.release()
