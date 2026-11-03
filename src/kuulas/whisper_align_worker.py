"""Isolated Podcast word alignment, also routed by the macOS app launcher."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(args: list[str] | None = None) -> int:
    import soundfile as sf  # noqa: PLC0415 - only in the alignment process
    import soxr  # noqa: PLC0415
    from wordalign import align_raw, make_aligner, refined  # noqa: PLC0415

    audio_path, raw_path, out_path = sys.argv[1:] if args is None else args
    samples, rate = sf.read(audio_path, dtype="float32", always_2d=True)
    mono = samples.mean(axis=1)
    audio = soxr.resample(mono, rate, 16000, quality="HQ") if rate != 16000 else mono
    raw = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    errors = []
    rows = align_raw(raw, audio, make_aligner(), errors=errors)
    aligned = sum(row["ctc_start"] is not None for row in rows)
    if rows and not aligned:
        raise RuntimeError("No Whisper words could be aligned: " + "; ".join(errors))
    Path(out_path).write_text(
        json.dumps({"words": refined(rows), "rejected": len(rows) - aligned},
                   ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
