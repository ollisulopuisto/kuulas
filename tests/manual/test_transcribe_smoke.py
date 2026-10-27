"""Manual transcription smoke test using local Orukeet.

Excluded from the default test run (``norecursedirs`` in pyproject.toml).
Requires the transcribe extra:

    uv sync --extra transcribe
    uv run pytest -q tests/manual/test_transcribe_smoke.py -s

Or run as a script:

    uv run python tests/manual/test_transcribe_smoke.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from kuulas import transcribe
from kuulas.clock import FLICKS

RATE = 16000
DURATION = 3.0
TEST_PHRASE = "Hello world, this is a kuulas transcription test."


def make_speech_like_wav(path: Path, seconds: float = DURATION, rate: int = RATE) -> Path:
    """Generate a short speech file via platform TTS or synthetic formants."""
    # 1. macOS 'say'
    say = shutil.which("say")
    if say:
        try:
            subprocess.run(  # noqa: S603
                [say, "-o", str(path), f"--data-format=LEF32@{rate}", TEST_PHRASE],
                check=True,
                capture_output=True,
            )
            if path.is_file() and path.stat().st_size > 100:
                return path
        except (subprocess.SubprocessError, OSError):
            pass

    # 2. Linux 'espeak' / 'espeak-ng'
    for cmd in ("espeak-ng", "espeak"):
        binary = shutil.which(cmd)
        if binary:
            try:
                subprocess.run(  # noqa: S603
                    [binary, "-w", str(path), "-s", "140", TEST_PHRASE],
                    check=True,
                    capture_output=True,
                )
                if path.is_file() and path.stat().st_size > 100:
                    return path
            except (subprocess.SubprocessError, OSError):
                pass

    # 3. Windows PowerShell System.Speech
    if sys.platform == "win32":
        ps = shutil.which("powershell")
        if ps:
            script = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.SetOutputToWaveFile('{path}'); "
                f"$s.Speak('{TEST_PHRASE}'); "
                f"$s.Dispose()"
            )
            try:
                subprocess.run(  # noqa: S603
                    [ps, "-Command", script], check=True, capture_output=True
                )
                if path.is_file() and path.stat().st_size > 100:
                    return path
            except (subprocess.SubprocessError, OSError):
                pass

    # 4. Fallback: synthetic formant pulse train with vocal tract harmonics
    n = int(seconds * rate)
    t = np.arange(n) / rate
    sig = np.zeros(n, dtype=np.float32)
    for harm in range(1, 25):
        freq = harm * 130
        gain = (np.exp(-((freq - 700) / 200) ** 2)
                + 0.6 * np.exp(-((freq - 1200) / 250) ** 2)
                + 0.3 * np.exp(-((freq - 2500) / 300) ** 2))
        sig += gain * np.sin(2 * np.pi * freq * t, dtype=np.float32)

    sig *= (0.5 + 0.5 * np.sin(2 * np.pi * 3.5 * t)).astype(np.float32)
    sig = sig / np.max(np.abs(sig)) * 0.5
    sf.write(str(path), sig, rate)
    return path


def test_transcribe_smoke_returns_words_in_flicks(tmp_path):
    wav_path = make_speech_like_wav(tmp_path / "speech_like.wav")
    assert wav_path.is_file()

    # Use the installed local Orukeet MLX model
    words = transcribe.local(wav_path, language="en")
    assert isinstance(words, list)
    assert len(words) > 0, "Expected at least one word from speech audio"

    info = sf.info(str(wav_path))
    max_flicks = round((info.duration + 1.0) * FLICKS)
    for word in words:
        assert isinstance(word["w"], str)
        assert word["w"].strip()
        assert isinstance(word["s"], int)
        assert word["s"] >= 0
        assert isinstance(word["e"], int)
        assert word["e"] > word["s"]
        assert word["e"] <= max_flicks
        assert isinstance(word["spk"], str)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        print("Running manual transcription smoke test...")
        tmp_dir = Path(td)
        test_transcribe_smoke_returns_words_in_flicks(tmp_dir)
        wav = tmp_dir / "speech_like.wav"
        words = transcribe.local(wav, language="en")
        print(f"Transcribed {len(words)} words:")
        for w in words:
            print(f"  [{w['s'] / FLICKS:.2f}s - {w['e'] / FLICKS:.2f}s]: {w['w']}")
        print("OK: manual transcription smoke test passed.")
