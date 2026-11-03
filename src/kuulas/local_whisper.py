"""Local Whisper transcription with Podcast's measured CTC word-time correction.

Whisper inference runs in this worker. The shared ``wordalign`` package runs in a
child process so its PyTorch libraries cannot conflict with CTranslate2.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from . import local_memory
from .clock import FLICKS
from .jobs import JobCancelledError
from .messages import KuulasError

DEFAULT_MODEL = "large-v3-turbo"



class WhisperError(KuulasError, RuntimeError):
    """Local Whisper or its required word alignment could not run."""


def _model_factory():
    try:
        from faster_whisper import WhisperModel  # noqa: PLC0415 - optional extra
    except ImportError as exc:
        raise WhisperError("error.transcribe.whisper_missing") from exc
    return WhisperModel


def _align_words(path: Path, raw: dict, progress=None) -> tuple[list[dict], int]:
    """Use Podcast's wordalign in an isolated process and return corrected words."""
    try:
        import wordalign  # noqa: F401, PLC0415 - optional local dependency
    except ImportError as exc:
        raise WhisperError("error.transcribe.whisper_alignment_missing") from exc

    with tempfile.TemporaryDirectory(prefix="kuulas-whisper-align-") as directory:
        root = Path(directory)
        raw_path, output_path = root / "raw.json", root / "aligned.json"
        raw_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(  # noqa: S603 - fixed interpreter and script, no shell
            [sys.executable, "-m", "kuulas.whisper_align_worker",
             str(path), str(raw_path), str(output_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            detail = (
                result.stderr or result.stdout or "word alignment exited unsuccessfully"
            )[-2000:]
            raise WhisperError("error.transcribe.whisper_alignment", error=detail.strip())
        try:
            aligned = json.loads(output_path.read_text(encoding="utf-8"))
            words = aligned["words"]
            rejected = int(aligned["rejected"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise WhisperError("error.transcribe.whisper_alignment",
                               error=f"Invalid wordalign result: {exc}") from exc
    if progress is not None:
        progress(0.99)
    return words, rejected


def local(path: str | Path, model: str = DEFAULT_MODEL,
          language: str | None = None, progress=None,
          cpu_threads: int | None = None, *,
          allow_low_memory: bool = False) -> list[dict]:
    """Transcribe with faster-whisper CPU int8, then correct word starts with Podcast.

    The turbo model is deliberately used without Whisper's short-audio ``-ac``
    optimization: podcast recordings must be decoded end to end.
    """
    try:
        return _transcribe(path, model, language, progress, cpu_threads, allow_low_memory)
    except (WhisperError, JobCancelledError):
        raise
    except Exception as exc:
        raise WhisperError("error.transcribe.whisper_failed",
                           error=f"{type(exc).__name__}: {exc}") from exc


def _transcribe(path, model, language, progress, cpu_threads, allow_low_memory):
    if not allow_low_memory and not local_memory.eligible():
        raise WhisperError("error.whisper.memory")
    source = Path(path).resolve()
    if not source.is_file():
        raise WhisperError("error.transcribe.whisper_failed",
                           error=f"Audio file not found: {source}")
    factory = _model_factory()
    options = {"device": "cpu", "compute_type": "int8"}
    if cpu_threads:
        options["cpu_threads"] = max(1, int(cpu_threads))
    recognizer = factory(model or DEFAULT_MODEL, **options)
    segments, info = recognizer.transcribe(
        str(source), language=language or None, word_timestamps=True,
        vad_filter=True,
    )
    raw_segments = []
    duration = max(0.0, float(getattr(info, "duration", 0) or 0))
    for segment in segments:
        if progress is not None and getattr(progress, "cancelled", False):
            raise JobCancelledError
        words = []
        for word in segment.words or []:
            if word.start is None or not str(word.word).strip():
                continue
            end = word.end if word.end is not None else word.start
            words.append({"word": word.word, "start": float(word.start),
                          "end": float(end)})
        if words:
            raw_segments.append({"words": words})
        if progress is not None and duration:
            progress(min(0.9, max(0.0, float(segment.end) / duration * 0.9)))
    if not raw_segments:
        raise WhisperError("error.transcribe.whisper_failed",
                           error="Whisper returned no word-timed speech.")
    try:
        aligned, _rejected = _align_words(source, {"segments": raw_segments}, progress)
    except WhisperError:
        raise
    except Exception as exc:
        raise WhisperError("error.transcribe.whisper_alignment",
                           error=f"{type(exc).__name__}: {exc}") from exc
    if not aligned:
        raise WhisperError("error.transcribe.whisper_alignment",
                           error="Word alignment returned no words.")
    output = []
    for word in aligned:
        start = round(float(word["start"]) * FLICKS)
        end = max(start + 1, round(float(word["end"]) * FLICKS))
        output.append({"w": str(word["word"]).strip(), "s": start,
                       "e": end, "spk": ""})
    output.sort(key=lambda item: (item["s"], item["e"]))
    if progress is not None:
        progress(1.0)
    return output
