"""Speech to word-timed text.

Backends produce ``[{"w", "s", "e", "spk"}]`` in *source* frames at the
project rate (see ``transcript``):

* ``local``: faster-whisper on this machine. Runs on Mac, Linux and Windows
  (CPU int8; CUDA when present). Install with ``uv sync --extra transcribe``.
* ``parse``: any word-timed JSON, e.g. from colab-transcribe, Whisper,
  WhisperX or an export from another editor.

Colab is not wired yet: see ROADMAP.md.
"""

from __future__ import annotations

from pathlib import Path

from .messages import KuulasError


def _word(text: str, start: float, end: float, rate: int, spk: str = "") -> dict:
    s = round(float(start) * rate)
    e = max(s + 1, round(float(end) * rate))
    return {"w": text.strip(), "s": s, "e": e, "spk": spk or ""}


def parse(data, rate: int) -> list[dict]:
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
        out.append(_word(str(text), start, end, rate, speaker))
    return out


def from_segments(segments, rate: int) -> list[dict]:
    return [_word(w.word, w.start, w.end, rate)
            for seg in segments for w in (seg.words or [])
            if w.word.strip()]


class TranscribeError(KuulasError, RuntimeError):
    """Transcription cannot run here: a required extra is not installed."""


def local(path: str | Path, rate: int, model: str = "small",
          language: str | None = None, progress=None) -> list[dict]:
    """Transcribe ``path`` with faster-whisper, word timestamps on."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TranscribeError("error.transcribe.missing_extra") from e
    whisper = WhisperModel(model, device="auto", compute_type="int8")
    segments, info = whisper.transcribe(str(path), language=language,
                                        word_timestamps=True, vad_filter=True)
    collected = []
    for seg in segments:
        collected.append(seg)
        if progress is not None and info.duration:
            progress(min(1.0, seg.end / info.duration))
    return from_segments(collected, rate)
