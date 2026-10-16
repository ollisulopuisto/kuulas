"""Rebuild the golden renders in ``tests/golden/``.

The golden renders pin down what the mix sounds like: small projects that
cover pan, fades, crossfades, clip envelopes, track automation, buses and
solo/mute, each with the stereo output of ``mixer.mix`` as a 32-bit float
WAV and its SHA-256 in ``manifest.json``. Any playback engine, the Python
one or a native one later (docs/PLAN.md, WP2), must reproduce them within
1e-6.

So regenerating them is a statement that the mix *should* sound different.
The script refuses to run unless you say so with ``--i-changed-the-mixer``,
and the commit that changes a golden file must say why.

    uv run python tests/golden/regenerate.py --i-changed-the-mixer
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np

from kuulas import mixer, ops
from kuulas.model import Media, Project

HERE = Path(__file__).resolve().parent
FLAG = "--i-changed-the-mixer"

#: A low rate keeps the files small (a second of stereo float is 64 kB); the
#: mixer does not depend on the rate.
RATE = 8000
SECONDS = 1


def sources() -> dict[str, np.ndarray]:
    """Deterministic source audio, ``(channels, frames)`` float32."""
    n = RATE * SECONDS
    t = np.arange(n) / RATE
    rng = np.random.default_rng(20261016)
    return {
        "tone": (0.5 * np.sin(2 * np.pi * 440 * t))[None, :].astype(np.float32),
        "noise": (0.2 * rng.standard_normal(n))[None, :].astype(np.float32),
        "stereo": np.stack([0.4 * np.sin(2 * np.pi * 330 * t),
                            0.3 * np.sin(2 * np.pi * 550 * t)]).astype(np.float32),
    }


def _base(audio: dict[str, np.ndarray]) -> Project:
    p = Project(rate=RATE)
    for media_id, a in audio.items():
        p = ops.add_media(p, Media(id=media_id, name=f"{media_id}.wav",
                                   channels=a.shape[0], frames=a.shape[1]))
    return p


def projects(audio: dict[str, np.ndarray]) -> dict[str, Project]:
    base = _base(audio)
    out: dict[str, Project] = {}

    p = ops.add_track(base, "t1", "Tone")
    p = ops.add_clip(p, "t1", "tone", clip_id="c1")
    p = ops.set_clip(p, "c1", pan=-0.6)
    p = ops.add_track(p, "t2", "Noise")
    p = ops.add_clip(p, "t2", "noise", clip_id="c2")
    p = ops.set_clip(p, "c2", pan=0.8)
    p = ops.add_track(p, "t3", "Music", kind="music")
    p = ops.add_clip(p, "t3", "stereo", clip_id="c3")
    out["pan"] = ops.set_track(p, "t3", pan=0.3)

    p = ops.add_track(base, "t1", "Tone")
    p = ops.add_clip(p, "t1", "tone", start=400, offset=200, length=6000,
                     clip_id="c1")
    out["fades"] = ops.set_clip(p, "c1", gain_db=-3.0, fade_in=1000, fade_out=1500)

    # A ripple delete in the middle of one clip leaves two clips joined by a
    # centred crossfade, the edit kuulas makes most.
    p = ops.add_track(base, "t1", "Noise")
    p = ops.add_clip(p, "t1", "noise", clip_id="c1")
    out["crossfades"] = ops.ripple_delete(p, 3000, 4000)

    p = ops.add_track(base, "t1", "Tone")
    p = ops.add_clip(p, "t1", "tone", clip_id="c1")
    out["envelopes"] = ops.set_clip_envelope(
        p, "c1", [(0, 0.0), (2000, -12.0), (5000, 3.0), (7000, -40.0)])

    p = ops.add_track(base, "t1", "Music", kind="music")
    p = ops.add_clip(p, "t1", "stereo", clip_id="c1")
    p = ops.set_track(p, "t1", gain_db=-2.0)
    out["automation"] = ops.set_track_automation(
        p, "t1", [(1000, 0.0), (3000, -20.0), (6000, -6.0)])

    p = ops.add_bus(base, "b1", "Voices")
    p = ops.add_bus(p, "b2", "Muted")
    p = ops.set_bus(p, "b1", gain_db=-4.0, pan=-0.5)
    p = ops.set_bus(p, "b2", mute=True)
    p = ops.add_track(p, "t1", "Tone")
    p = ops.add_clip(p, "t1", "tone", clip_id="c1")
    p = ops.set_track(p, "t1", bus="b1")
    p = ops.add_track(p, "t2", "Noise")
    p = ops.add_clip(p, "t2", "noise", clip_id="c2")
    p = ops.set_track(p, "t2", bus="b2")
    p = ops.add_track(p, "t3", "Music", kind="music")
    p = ops.add_clip(p, "t3", "stereo", clip_id="c3")
    out["buses"] = ops.set_master(p, -1.5)

    p = ops.add_track(base, "t1", "Tone")
    p = ops.add_clip(p, "t1", "tone", clip_id="c1")
    p = ops.add_track(p, "t2", "Noise")
    p = ops.add_clip(p, "t2", "noise", clip_id="c2")
    p = ops.set_track(p, "t2", mute=True)
    p = ops.add_track(p, "t3", "Music", kind="music")
    p = ops.add_clip(p, "t3", "stereo", start=0, length=4000, clip_id="c3")
    p = ops.add_clip(p, "t3", "stereo", start=4000, offset=4000, clip_id="c4")
    p = ops.set_clip(p, "c4", muted=True)
    out["mute"] = p
    # Solo overrides mute: the muted noise track is heard because it is soloed.
    out["solo"] = ops.solo(p, "t2", exclusive=False)
    return out


def write_float_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    """``(channels, frames)`` as a plain 32-bit float WAV, byte for byte the
    same every time. libsndfile adds a PEAK chunk stamped with the time of
    writing, so its files never hash the same twice."""
    data = np.ascontiguousarray(audio.T, dtype="<f4").tobytes()
    channels = audio.shape[0]
    fmt = struct.pack("<HHIIHH", 3, channels, rate, rate * 4 * channels,
                      4 * channels, 32)
    body = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"data" + struct.pack("<I", len(data)) + data)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MemoryStore:
    def __init__(self, arrays: dict[str, np.ndarray]):
        self.arrays = arrays

    def read(self, media_id: str, first: int, count: int) -> np.ndarray:
        a = self.arrays[media_id]
        out = np.zeros((a.shape[0], count), dtype=np.float32)
        lo, hi = max(0, first), min(a.shape[1], first + count)
        if hi > lo:
            out[:, lo - first:hi - first] = a[:, lo:hi]
        return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(FLAG, dest="changed", action="store_true",
                        help="confirm that the mix is meant to sound different")
    args = parser.parse_args(argv)
    if not args.changed:
        print(f"Refusing to rewrite the golden renders without {FLAG}.\n"
              "They are what every engine must reproduce; regenerate them only\n"
              "when the mixer is meant to sound different, and say why in the\n"
              "commit.", file=sys.stderr)
        return 2

    audio = sources()
    (HERE / "media").mkdir(exist_ok=True)
    manifest: dict = {"rate": RATE, "media": {}, "renders": {}}
    for media_id, a in audio.items():
        path = HERE / "media" / f"{media_id}.wav"
        write_float_wav(path, a, RATE)
        manifest["media"][media_id] = sha256(path)
    store = MemoryStore(audio)
    for name, p in projects(audio).items():
        (HERE / f"{name}.json").write_text(p.to_json() + "\n", encoding="utf-8")
        frames = p.length
        out = mixer.mix(p, store, 0, frames)
        path = HERE / f"{name}.wav"
        write_float_wav(path, out, RATE)
        manifest["renders"][name] = {"frames": frames, "sha256": sha256(path)}
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                        encoding="utf-8")
    print(f"Wrote {len(manifest['renders'])} golden renders to {HERE}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
