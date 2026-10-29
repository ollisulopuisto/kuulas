#!/usr/bin/env python3
"""Explicit opt-in whole-Session -16 LUFS candidate acceptance, no default change.

Run one duration per fresh process. Uses generated stereo media, real project
import/mixer, disk-backed global master, final WAV writer and metadata report.
This complements, not repeats, speechmix API/MLX acceptance. Requires sufficient
free scratch space; refuses before allocating the long fixture when too small.
"""
from __future__ import annotations

import argparse
import json
import shutil
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir

import numpy as np
import psutil
import soundfile as sf
from speechmix.meter import IntegratedMeter

from kuulas import export
from kuulas.session import Session

RATE = 48000


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(minutes: int, root: Path) -> dict:
    frames = minutes * 60 * RATE
    required = export._master_disk_bytes(frames, 2) + frames * 2 * 4
    free = shutil.disk_usage(root).free
    if free < required:
        return {'minutes': minutes, 'status': 'insufficient_disk',
                'required_bytes': required, 'free_bytes': free}
    with TemporaryDirectory(prefix='kuulas-master-accept-', dir=root) as directory:
        folder = Path(directory)
        source = folder / 'synthetic.wav'
        t = np.arange(RATE) / RATE
        # Within the recipe's maximum lift; constant asymmetric stereo makes
        # channel swaps and pan mistakes apparent without full input allocation.
        wave = (.1 * np.sin(2 * np.pi * 137 * t)
                + .05 * np.sin(2 * np.pi * 911 * t)).astype(np.float32)
        block = np.column_stack([wave, wave * .6])
        with sf.SoundFile(source, 'w', RATE, 2, subtype='FLOAT') as output:
            for _ in range(minutes * 60):
                output.write(block)
        session = Session(folder / 'acceptance.kuulas')
        stop = threading.Event()
        process = psutil.Process()
        peaks = {'rss': process.memory_info().rss, 'disk': 0}
        try:
            session.import_media([str(source)])
            # This process alone opts in. No config, user preference, production
            # default or stored project flag changes.
            require(export.STREAM_MASTERING_ENABLED is False, "Legacy default changed")
            export.STREAM_MASTERING_ENABLED = True
            # Acceptance-only bypass: the production preflight estimates the old
            # full-length algorithm. Measure the candidate here, do not ship a
            # guessed replacement RAM threshold or change legacy protection.
            export.master_fits = lambda *_args, **_kwargs: True
            baseline = process.memory_info().rss

            def monitor():
                while not stop.wait(.1):
                    peaks['rss'] = max(peaks['rss'], process.memory_info().rss)
                    size = 0
                    for path in folder.rglob('*'):
                        try:
                            if path.is_file():
                                size += path.stat().st_size
                        except FileNotFoundError:
                            pass
                    peaks['disk'] = max(peaks['disk'], size)

            thread = threading.Thread(target=monitor)
            thread.start()
            started = time.monotonic()
            try:
                result = session.export({'kind': 'mix', 'format': 'wav',
                    'bit_depth': 32, 'master_lufs': -16.,
                    'folder': str(folder / 'output')})
            finally:
                stop.set()
                thread.join()
            elapsed = time.monotonic() - started
            meter = IntegratedMeter(RATE)
            energy = np.zeros(2)
            count, peak = 0, 0.
            with sf.SoundFile(result['path']) as output:
                require(output.frames == frames, "Wrong output length")
                require(output.samplerate == RATE and output.channels == 2,
                        "Wrong format")
                for audio in output.blocks(blocksize=RATE):
                    meter.add(audio.T)
                    energy += np.sum(audio * audio, axis=0)
                    count += len(audio)
                    peak = max(peak, float(np.max(np.abs(audio))))
            leftovers = [str(p.relative_to(folder)) for p in folder.rglob('*.partial')]
            require(count == frames and not leftovers,
                    "Output incomplete or scratch leaked")
            loudness = meter.value()
            require(result['master']['reached'] and abs(loudness + 16) <= .5,
                    'Target loudness not reached')
            rms = np.sqrt(energy / count)
            require(abs(rms[1] / rms[0] - .6) < 1e-5, 'Stereo balance changed')
            return {'status': 'passed', 'legacy_guard_bypassed_for_measurement': True,
                    'minutes': minutes, 'frames': frames,
                    'baseline_rss': baseline, 'peak_rss': peaks['rss'],
                    'incremental_peak_rss': peaks['rss'] - baseline,
                    'disk_peak_bytes': peaks['disk'], 'elapsed_s': elapsed,
                    'measured_lufs': loudness, 'master': result['master'],
                    'channel_rms': rms.tolist(), 'sample_peak': peak,
                    'partial_left': leftovers}
        finally:
            stop.set()
            session.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes', type=int, choices=(1, 10, 30, 90), required=True)
    parser.add_argument('--scratch', type=Path, default=Path(gettempdir()))
    args = parser.parse_args()
    print(json.dumps(run(args.minutes, args.scratch)), flush=True)
