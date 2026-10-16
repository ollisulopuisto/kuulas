"""Broken and awkward audio files for the import fault-injection tests (WP34).

Generated into a scratch folder by ``make_all`` (a few seconds of audio each,
all under 200 KB), so no binary blobs live in git. Every file is
deterministic: the noise comes from a fixed seed.

    truncated.wav        the header promises 2 s, the bytes stop at 60 %
    garbage.wav          random bytes behind a .wav name
    empty.wav            zero bytes
    junk_middle.mp3      a 6 s MP3 with random bytes over a fifth of it
    video_no_audio.mp4   a video with a video stream only
    six_channel.wav      six channels of noise
    nonsense_bwf.wav     a BWF ``bext`` TimeReference of 2**40 samples (~254 days)
    float32.wav          32-bit float samples at the project rate
    silent.wav           one second of digital silence
"""

import os
import struct
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from speechmix.binaries import get_binary_path

RATE = 48000


def noise(seconds: float, channels: int = 1, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    shape = (round(seconds * RATE), channels)
    return (rng.standard_normal(shape) * 0.1).astype(np.float32)


def ffmpeg(*args) -> None:
    # Fixed argv, no shell; the binary is the one the app itself uses.
    subprocess.run([get_binary_path("ffmpeg"), "-v", "error", "-y", *args],  # noqa: S603
                   check=True)


def add_bext(path: Path, time_reference: int) -> None:
    """Append a minimal BWF ``bext`` chunk with this TimeReference."""
    data = path.read_bytes()
    bext = bytearray(602)
    struct.pack_into("<Q", bext, 338, time_reference)
    chunk = b"bext" + struct.pack("<I", len(bext)) + bytes(bext)
    body = data[12:] + chunk
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body)


def make_all(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = {name: folder / name for name in (
        "truncated.wav", "garbage.wav", "empty.wav", "junk_middle.mp3",
        "video_no_audio.mp4", "six_channel.wav", "nonsense_bwf.wav",
        "float32.wav", "silent.wav")}

    sf.write(out["truncated.wav"], noise(2.0), RATE, subtype="PCM_16")
    whole = out["truncated.wav"].read_bytes()
    out["truncated.wav"].write_bytes(whole[: len(whole) * 6 // 10])

    out["garbage.wav"].write_bytes(np.random.default_rng(1).bytes(3000))
    out["empty.wav"].write_bytes(b"")

    ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=6", "-c:a", "libmp3lame",
           "-b:a", "64k", str(out["junk_middle.mp3"]))
    mp3 = bytearray(out["junk_middle.mp3"].read_bytes())
    third, fifth = len(mp3) // 3, len(mp3) // 5
    mp3[third:third + fifth] = np.random.default_rng(2).bytes(fifth)
    out["junk_middle.mp3"].write_bytes(bytes(mp3))

    ffmpeg("-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
           "-c:v", "mpeg4", str(out["video_no_audio.mp4"]))

    sf.write(out["six_channel.wav"], noise(0.3, channels=6, seed=3), RATE,
             subtype="PCM_16")

    sf.write(out["nonsense_bwf.wav"], noise(1.0, seed=4), RATE, subtype="PCM_16")
    add_bext(out["nonsense_bwf.wav"], 2 ** 40)

    sf.write(out["float32.wav"], noise(0.5, seed=5), RATE, subtype="FLOAT")
    sf.write(out["silent.wav"], np.zeros((RATE, 1), np.float32), RATE, subtype="PCM_16")
    return out


if __name__ == "__main__":
    import sys
    made = make_all(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("broken-out"))
    for name, path in made.items():
        print(f"{name}: {os.path.getsize(path)} bytes")
