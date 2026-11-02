"""Per-user Orukeet setup: verified downloads, atomic publication and model selection."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import ssl
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

import certifi

from . import local_memory
from .messages import KuulasError, config_dir
from .package import write_json_atomic

REPOSITORY = "itsreidar/orukeet-mlx"
REVISION = "17894066e1d148997bfc93a4d41c605ca1b0475d"
MODEL_URL = f"https://huggingface.co/{REPOSITORY}"
CHUNK = 1024 * 1024
SPACE_MARGIN = 64 * CHUNK
_LOCK = threading.Lock()


@dataclass(frozen=True)
class ModelFile:
    name: str
    size: int
    sha256: str


FILES = (
    ModelFile("config.json", 244093,
              "f320f1292511f34ec47f513755fe20fd01dbfc09a925d42730e66059a6e1ef4c"),
    ModelFile("model.safetensors", 1254183820,
              "ea97a67e3dfd4593481254c2543a9b4aff3d0842534cbac5356e710e482d2074"),
    ModelFile("tokenizer.model", 360916,
              "eacec2b0a77f336d4a2ca4a25a7047575d3c2b74de47e997f4c205126ed3135e"),
    ModelFile("tokenizer.vocab", 101024,
              "41130ff456706304a1adec782ccc9e003c4d417e8e324353d281be958cac4e17"),
    ModelFile("vocab.txt", 46772,
              "3cde1409fd78783a79b29ed4d32da57c746993856f7c8263bcb905d2e5839db7"),
    ModelFile("LICENSE", 1094,
              "e7349d7fc331c670e274335beaaa843d6d9bbeeb12691f1f40144c6214459bad"),
    ModelFile("LICENSE-WEIGHTS", 20137,
              "23ee78c8bae49cf08ea2f0c84945c66b987ebe4520881fb51b3dad4fb43d07c2"),
    ModelFile("NOTICE.md", 4765,
              "f1cf43822e52f0a2e5aa3c0b1252d34a17d30cd29303a12eb2f0b151e7433132"),
    ModelFile("README.md", 1428,
              "c829e3e6abf306cf6174e5e9691a612ca9121adc7d17623ba1a89626a3b38faa"),
    ModelFile("CITATION.cff", 1388,
              "9dd2b4e1fd368a4254768e72fe0a99b2e29d53947b88ad260e8050861373e3a8"),
)


class ModelError(KuulasError, ValueError):
    """The model cannot be installed or selected; shown in the setup dialog."""


def settings_file() -> Path:
    override = os.environ.get("KUULAS_ORUKEET_FILE")
    return Path(override) if override else config_dir() / "orukeet.json"


def model_path() -> Path:
    try:
        data = json.loads(settings_file().read_text(encoding="utf-8"))
        selected = data.get("model") if isinstance(data, dict) else None
        if isinstance(selected, str) and selected and "\0" not in selected:
            return Path(selected).expanduser()
    except (OSError, ValueError):
        pass
    return Path.home() / ".models" / "orukeet-mlx"


def valid_model(folder: Path) -> bool:
    try:
        config = folder / "config.json"
        if config.stat().st_size > 4 * CHUNK:
            return False
        data = json.loads(config.read_text(encoding="utf-8"))
        return (isinstance(data, dict) and "RNNT" in str(data.get("target", ""))
                and (folder / "model.safetensors").stat().st_size >= 8)
    except (OSError, ValueError):
        return False


def status() -> dict:
    path = model_path()
    return {"ready": valid_model(path), "path": str(path),
            "supported": platform.system() == "Darwin" and platform.machine() == "arm64",
            "eligible": local_memory.eligible(),
            "memory_minimum_bytes": local_memory.MINIMUM_BYTES,
            "bytes": sum(file.size for file in FILES), "source": MODEL_URL,
            "revision": REVISION}


def select_model(folder: object) -> dict:
    if not isinstance(folder, str) or not folder or "\0" in folder:
        raise ModelError("error.orukeet.invalid_model")
    path = Path(folder).expanduser()
    if not path.is_absolute() or not valid_model(path):
        raise ModelError("error.orukeet.invalid_model")
    resolved = path.resolve()
    # resolve follows symlinks: confirm the resolved path is still a directory
    # (CodeQL py/path-injection).
    if not resolved.is_dir():
        raise ModelError("error.orukeet.invalid_model")
    write_json_atomic(settings_file(), {"model": str(resolved)})
    return status()


def download_context() -> ssl.SSLContext:
    """Keep system/custom trust and add CA roots shipped with the packaged app."""
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context


def install(progress) -> dict:
    """Download fixed artifacts; a partial download never becomes the selected model.

    The staging tree is ours alone. Old models (including symlinks into other
    applications' folders) are never overwritten or removed.
    """
    if not status()["supported"]:
        raise ModelError("error.orukeet.platform")
    if not _LOCK.acquire(blocking=False):
        raise ModelError("error.orukeet.busy")
    try:
        root = config_dir() / "models"
        root.mkdir(parents=True, exist_ok=True)
        total = sum(file.size for file in FILES)
        if shutil.disk_usage(root).free < total + SPACE_MARGIN:
            raise ModelError("error.orukeet.space")
        context = download_context()
        done = 0
        with tempfile.TemporaryDirectory(prefix=".orukeet-", dir=root) as temp:
            staging = Path(temp)
            for item in FILES:
                digest, received = hashlib.sha256(), 0
                url = f"{MODEL_URL}/resolve/{REVISION}/{item.name}"
                progress(0.99 * done / total)
                # Fixed HTTPS origin/revision/filenames; nothing supplied by a request.
                with urlopen(url, timeout=20, context=context) as response, (  # noqa: S310
                    staging / item.name).open("xb") as target:
                    while chunk := response.read(CHUNK):
                        received += len(chunk)
                        if received > item.size:
                            raise ModelError("error.orukeet.verify", name=item.name)
                        target.write(chunk)
                        digest.update(chunk)
                        progress(0.99 * (done + received) / total)
                if received != item.size or digest.hexdigest() != item.sha256:
                    raise ModelError("error.orukeet.verify", name=item.name)
                done += received
            if not valid_model(staging):
                raise ModelError("error.orukeet.invalid_model")
            progress(0.999)
            target = root / f"orukeet-mlx-{REVISION[:12]}-{uuid.uuid4().hex}"
            staging.rename(target)
            # TemporaryDirectory's original path no longer exists; only the fully
            # checked directory is published, and preferences change last.
            select_model(str(target))
        progress(1.0)
        return status()
    except OSError as error:
        raise ModelError("error.orukeet.download", error=str(error)) from error
    finally:
        _LOCK.release()
