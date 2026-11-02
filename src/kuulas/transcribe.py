"""Speech to word-timed text.

Backends produce ``[{"w", "s", "e", "spk"}]`` with times in flicks from the
media's start: the recording clock (``clock``), so the words never change
when the project rate does (see ``transcript``):

* ``local``: Orukeet on this Apple-silicon Mac, through Kuulas's native SDK
  worker and its word timings.
* ``parse``: any word-timed JSON, e.g. from colab-transcribe, Whisper,
  WhisperX or an export from another editor.

Colab transcription uses the same tool through ``colab_transcribe``.
"""

from __future__ import annotations

from pathlib import Path

import soundfile as sf

from . import live_engine, local_memory, local_models
from .clock import FLICKS
from .jobs import JobCancelledError
from .messages import KuulasError

_LOCAL_CHUNK_S = 30
_LOCAL_CONTEXT_S = 1


def _word(text: str, start: float, end: float, spk: str = "") -> dict:
    s = round(float(start) * FLICKS)
    # A word always has some length; the timeline makes that at least a frame.
    e = max(s + 1, round(float(end) * FLICKS))
    return {"w": text.strip(), "s": s, "e": e, "spk": spk or ""}


def _check_local_cancelled(progress) -> None:
    if progress is not None and getattr(progress, "cancelled", False):
        raise JobCancelledError


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


def local(path: str | Path, model: str = "small",
          language: str | None = None, progress=None,
          cpu_threads: int | None = None, *,
          allow_low_memory: bool = False) -> list[dict]:
    """Transcribe locally with Orukeet's native word timings, without CTC alignment.

    The old shared CLI route ran a second CTC alignment pass after Orukeet and
    failed whole takes when that pass rejected every word. Reuse the same native
    worker as live transcription and process bounded windows from the stored
    lossless media.
    """
    if not allow_low_memory and not local_memory.eligible():
        raise TranscribeError("error.orukeet.memory")
    # Retain persisted job arguments; Orukeet's installed SDK chooses its model
    # and owns CPU scheduling.
    _ = model, language, cpu_threads
    installation = local_models.status()
    if not installation["supported"]:
        raise TranscribeError("error.orukeet.platform")
    if not installation["ready"]:
        raise TranscribeError("error.transcribe.orukeet_model",
                              path=str(local_models.installation_file()))
    source = Path(path).resolve()
    receipt = live_engine.read_receipt()
    if receipt is None:
        raise TranscribeError("error.transcribe.orukeet_model",
                              path=str(local_models.installation_file()))
    engine = None
    try:
        _check_local_cancelled(progress)
        engine = live_engine.warm_engine_factory(receipt)
        words = []
        with sf.SoundFile(source) as audio:
            rate = int(audio.samplerate)
            total_frames = len(audio)
            core_frames = max(1, rate * _LOCAL_CHUNK_S)
            context_frames = rate * _LOCAL_CONTEXT_S
            core_start = 0
            while core_start < total_frames:
                _check_local_cancelled(progress)
                core_end = min(total_frames, core_start + core_frames)
                read_start = max(0, core_start - context_frames)
                read_end = min(total_frames, core_end + context_frames)
                audio.seek(read_start)
                samples = audio.read(read_end - read_start, dtype="float32",
                                     always_2d=True)
                mono = samples.mean(axis=1)
                chunk_words = engine(mono, rate)
                core_from_s = (core_start - read_start) / rate
                core_to_s = (core_end - read_start) / rate
                offset_s = read_start / rate
                for item in chunk_words:
                    try:
                        start = float(item["start"])
                        end = float(item["end"])
                        text = str(item.get("word", item.get("text", ""))).strip()
                    except (KeyError, TypeError, ValueError):
                        continue
                    midpoint = (start + end) / 2
                    if not text or not (core_from_s <= midpoint < core_to_s):
                        continue
                    words.append(_word(text, offset_s + start, offset_s + end,
                                       str(item.get("speaker", ""))))
                core_start = core_end
                if callable(progress):
                    progress(core_end / max(1, total_frames))
    except (TranscribeError, JobCancelledError):
        raise
    except Exception as error:
        raise TranscribeError("error.transcribe.orukeet_failed",
                              error=f"{type(error).__name__}: {error}") from error
    finally:
        close = getattr(engine, "close", None)
        if callable(close):
            close()
    words.sort(key=lambda word: (word["s"], word["e"]))
    return words
