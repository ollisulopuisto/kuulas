"""Speech to word-timed text.

Backends produce ``[{"w", "s", "e", "spk"}]`` with times in flicks from the
media's start: the recording clock (``clock``), so the words never change
when the project rate does (see ``transcript``):

* ``local``: Orukeet on this Apple-silicon Mac, through the podcast repo's
  shared CLI. MLX dependencies run in the tool's isolated environment.
* ``parse``: any word-timed JSON, e.g. from colab-transcribe, Whisper,
  WhisperX or an export from another editor.

Colab transcription uses the same tool through ``colab_transcribe``.
"""

from __future__ import annotations

from pathlib import Path

from . import colab_transcribe, local_memory, local_models
from .automix import run_process as _run_local_process
from .clock import FLICKS
from .messages import KuulasError


def _word(text: str, start: float, end: float, spk: str = "") -> dict:
    s = round(float(start) * FLICKS)
    # A word always has some length; the timeline makes that at least a frame.
    e = max(s + 1, round(float(end) * FLICKS))
    return {"w": text.strip(), "s": s, "e": e, "spk": spk or ""}


def parse(data) -> list[dict]:
    """Word-timed JSON (seconds) in the common shapes, to stored words."""
    if isinstance(data, dict):
        if "segments" in data:
            items = [w for seg in data["segments"] for w in seg.get("words", [])]
        else:
            items = data.get("words", [])
    else:
        items = data
    out = []
    for item in items:
        text = item.get("word", item.get("text", item.get("w", "")))
        start = item.get("start", item.get("s"))
        end = item.get("end", item.get("e", start))
        if start is None or not str(text).strip():
            continue
        speaker = item.get("speaker", item.get("spk", ""))
        out.append(_word(str(text), start, end, speaker))
    return out


def from_segments(segments) -> list[dict]:
    return [_word(w.word, w.start, w.end)
            for seg in segments for w in (seg.words or [])
            if w.word.strip()]


class TranscribeError(KuulasError, RuntimeError):
    """Transcription cannot run here: a required extra is not installed."""


class _LocalCancel:
    """Adapt the worker's progress cancellation without a second watcher thread."""

    def __init__(self, progress):
        self.progress = progress

    def is_set(self) -> bool:
        return bool(getattr(self.progress, "cancelled", False))


def local(path: str | Path, model: str = "small",
          language: str | None = None, progress=None,
          cpu_threads: int | None = None, allow_low_memory: bool = False) -> list[dict]:
    """Run shared local Orukeet; legacy Whisper model sizes select the Orukeet default.

    Explicit model paths are supported. Never accept the shared CLI's generic
    Parakeet fallback when the user's converted Orukeet model is missing.
    """
    if not allow_low_memory and not local_memory.eligible():
        raise TranscribeError("error.orukeet.memory")
    _ = cpu_threads  # MLX owns scheduling; retained for persisted jobs and callers.
    legacy = {"", "tiny", "base", "small", "medium", "large", "large-v2", "large-v3",
              "turbo", "orukeet"}
    model_path = (local_models.model_path()
                  if model in legacy else Path(model).expanduser())
    if not model_path.is_dir():
        raise TranscribeError("error.transcribe.orukeet_model", path=str(model_path))
    command = colab_transcribe.default_command()
    # Resolve optional MLX dependencies outside the editor/bundle environment.
    if command[0] == "uvx":
        command[1:1] = ["--with", "parakeet-mlx>=0.3.0", "--with", "lxml"]
    elif command[:2] == ["uv", "run"]:
        command[2:2] = ["--frozen", "--extra", "parakeet"]

    def report(fraction, *_args, **_kwargs):
        if callable(progress):
            progress(fraction)

    source = Path(path).resolve()
    settings = {"command": command, "align": False,
                "extra_args": ["--backend", "orukeet",
                               "--orukeet-model", str(model_path)]}
    if allow_low_memory:
        settings["extra_args"].append("--allow-low-memory")
    try:
        result = colab_transcribe.run(
            [{"id": "local", "name": source.name, "path": str(source)}],
            {"backend": "orukeet", "language": language}, settings, report,
            _LocalCancel(progress), run_process=_run_local_process)
    except colab_transcribe.ColabError as error:
        raise TranscribeError("error.transcribe.orukeet_failed",
                              error=str(error)) from error
    return result["results"]["local"]["words"]
