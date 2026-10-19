"""Hardware smoke test: record 5 seconds from the default input through the
whole recorder (supervisor, worker, real CoreAudio device).

Not part of the default run (``norecursedirs`` in pyproject.toml). Run it by
hand on a Mac with a microphone (the terminal needs microphone permission:
System Settings > Privacy & Security > Microphone), and speak or clap:

    uv run pytest -q -s tests/hardware/test_record.py

It prints the device, the levels it saw and where the files are. It fails,
loudly, if there is no input device or the device is not at 48 kHz (set it in
Audio MIDI Setup). The take is written to a temporary folder and kept so you
can listen to it; the path is printed.
"""

import json
import os
import shutil
import signal
import tempfile
import time
from pathlib import Path

import soundfile as sf

from kuulas_recorder.client import RecorderClient, spawn_supervisor
from kuulas_recorder.sources import input_devices

RATE = 48000
SECONDS = 5


def test_record_five_seconds_from_the_default_input():
    devices = input_devices()
    default = [d for d in devices if d.get("default")]
    assert default, f"No default input device; inputs seen: {devices}"
    print(f"\ndefault input: {default[0]}")
    folder = Path(tempfile.mkdtemp(prefix="kuulas-record-"))
    sock_dir = Path(tempfile.mkdtemp(prefix="kr"))
    proc = spawn_supervisor(sock_dir / "s.sock", state_dir=sock_dir,
                            env=os.environ.copy())
    peaks = []
    try:
        with RecorderClient.connect(sock_dir / "s.sock") as c:
            c.request("subscribe")
            st = c.request("start", folder=str(folder), take="hw", channels=[1],
                           names=["Mic"], rate=RATE)
            print(f"recording from {st['device']['name']} for {SECONDS} s...")
            end = time.monotonic() + SECONDS
            while time.monotonic() < end:
                time.sleep(0.5)
                peaks.append(c.request("levels")["peak_dbfs"][0])
            answer = c.request("stop")
            warnings = []
            while (ev := c.next_event(0.1)) is not None:
                if ev["event"] in ("warning", "error", "device_lost", "gap"):
                    warnings.append(ev)
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(20)
        shutil.rmtree(sock_dir, ignore_errors=True)
    snap = json.loads((folder / "hw.take.json").read_text())
    info = sf.info(folder / "hw-Mic.wav")
    print(f"levels (dBFS, every 0.5 s): {peaks}")
    print(f"file: {folder / 'hw-Mic.wav'}  {info.frames / RATE:.2f} s, {info.subtype}")
    print(f"overflows {snap['overflows']}, gaps {snap['gaps']}, warnings {warnings}")
    assert answer["take"]["stop_reason"] == "stopped"
    assert info.samplerate == RATE
    assert info.subtype == "PCM_24"
    assert abs(info.frames - SECONDS * RATE) < RATE // 2
    assert snap["overflows"] == 0
    assert max(peaks) > -90, "silence only: check the microphone permission"
