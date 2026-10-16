"""How ``v0-project/`` was made: a project folder in the pre-v1 layout.

Run once with kuulas 26.10.16.4 (commit c9bfc6b), the last version that
wrote this layout; it does not run against v1 code, which is the point of
the fixture. Kept so the fixture's contents can be read, not regenerated.

    uv run python tests/fixtures/make_v0_project.py <scratch dir>

The folder holds what today's code writes: ``project.sqlite`` (nodes, meta,
transcripts), ``media/<id>.json``, ``<id>.flac``, ``<id>.peaks.npy`` and
``seen.json``. One media is linked (its source is deleted afterwards, so it
is missing), one is a working FLAC.
"""

import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from kuulas import ops
from kuulas.history import History
from kuulas.media import MediaStore

RATE = 48000


def main(scratch: Path) -> None:
    out = Path(__file__).resolve().parent / "v0-project"
    shutil.rmtree(out, ignore_errors=True)
    (out / "media").mkdir(parents=True)
    rng = np.random.default_rng(29)
    anna = scratch / "anna.wav"
    ville = scratch / "ville.wav"
    sf.write(anna, (rng.standard_normal(4800) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    sf.write(ville, (rng.standard_normal(4800) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    store = MediaStore(out / "media", rate=RATE)
    a = store.import_file(anna, copy=True)  # working FLAC
    v = store.import_file(ville)            # linked in place
    h = History(out / "project.sqlite")
    p = h.state
    for m in (a, v):
        p = ops.add_media(p, m)
    h.commit("import", p)
    p = ops.add_track(p, track_id="A", name="Anna")
    p = ops.add_track(p, track_id="V", name="Ville")
    p = ops.add_clip(p, "A", a.id, clip_id="ca")
    p = ops.add_clip(p, "V", v.id, clip_id="cv", start=120)
    h.commit("clips", p)
    p = ops.mark_in_sync(p, ["ca", "cv"], main="ca", group_id="g1")
    h.commit("sync", p)
    rev = h.add_transcript(a.id, [{"w": "hei", "s": 480, "e": 1200, "spk": "A"},
                                  {"w": "maailma", "s": 1440, "e": 2400, "spk": "A"}])
    p = ops.set_transcript(p, a.id, rev)
    h.commit("transcript", p)
    p = ops.split_clip(p, "cv", at=2400, new_id="cv2")
    h.commit("split", p)
    h.undo()
    p = ops.set_master(h.state, -3.0)
    h.commit("master", p)
    rev2 = h.add_transcript(a.id, [{"w": "hei", "s": 480, "e": 1200, "spk": "A"},
                                   {"w": "maailma!", "s": 1440, "e": 2400, "spk": "A"}])
    h.commit("correction", ops.set_transcript(h.state, a.id, rev2))
    h.close()
    ville.unlink()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
