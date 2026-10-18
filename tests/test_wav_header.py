"""The WAV files the exporter writes must have a valid RIFF header (macOS Quick Look and
CoreAudio refuse a file whose RIFF size is wrong; audio editors forgive it)."""

import struct
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import export


def _chunks(raw: bytes) -> list[tuple[bytes, int, int]]:
    assert raw[:4] == b"RIFF"
    assert raw[8:12] == b"WAVE"
    out, at = [], 12
    while at + 8 <= len(raw):
        cid, size = raw[at:at + 4], struct.unpack("<I", raw[at + 4:at + 8])[0]
        out.append((cid, size, at + 8))
        at += 8 + size + (size & 1)
    assert at == len(raw), "no stray bytes after the last chunk"
    return out


@pytest.mark.parametrize(("channels", "bit_depth", "frames"),
                         [(1, 24, 48001), (1, 24, 48000), (2, 24, 48001), (1, 16, 4801),
                          (2, 16, 4801), (1, 32, 4801)])
def test_riff_header_is_valid(tmp_path: Path, channels, bit_depth, frames):
    path = tmp_path / "t.wav"
    writer = export._WavWriter(path, 48000, channels, bit_depth, 0, "test")
    x = (np.sin(np.arange(frames) * 0.05) * 0.3).astype("float32")
    writer.write(np.tile(x, (channels, 1)))
    writer.close()
    raw = path.read_bytes()
    assert struct.unpack("<I", raw[4:8])[0] == len(raw) - 8
    chunks = {cid: (size, start) for cid, size, start in _chunks(raw)}
    width = bit_depth // 8 * channels
    assert chunks[b"data"][0] == frames * width
    assert len(raw) % 2 == 0, "an odd data chunk is padded to an even length"
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    assert rate == 48000
    assert data.shape == (frames, channels)
