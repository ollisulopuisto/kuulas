"""Record explicit mixer output for the synthetic native-player fixture.

This never opens the source database through SQLite. All SQLite access is to a
private snapshot. The source audio is immutable generated PCM, not user data.
Regeneration changes need review, not automatic blessing after native failures.
"""
import importlib.util
import json
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from kuulas import mixer
from kuulas.history import History

ROOT = Path(__file__).resolve().parents[1] / 'Conformance'


class FixtureStore:
    """Known synthetic source, deliberately no relinking, caching or writes."""

    def __init__(self, path):
        self.audio, self.rate = sf.read(path, dtype='float32', always_2d=True)

    def read(self, _media_id, first, count):
        output = np.zeros((self.audio.shape[1], count), dtype=np.float32)
        lo, hi = max(0, first), min(len(self.audio), first + count)
        if hi > lo:
            output[:, lo - first:hi - first] = self.audio[lo:hi].T
        return output


def expected_audio():
    spec = importlib.util.spec_from_file_location(
        'snapshot', Path(__file__).with_name('snapshot.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    store = FixtureStore(ROOT / 'Session.kuulas' / 'recordings' / 'tone.wav')
    windows = [(2399, 5), (2640, 5), (2998, 5), (3198, 5), (3398, 5),
               (3500, 5), (4678, 5), (4797, 5)]
    result = {'rate': store.rate, 'tolerance': 0.000001, 'edits': []}
    with (module.snapshot(ROOT / 'Session.kuulas') as db,
          tempfile.TemporaryDirectory() as d):
        destination = Path(d) / 'project.sqlite'
        # backup into a second PRIVATE db for the existing History API.
        output = sqlite3.connect(destination)
        db.backup(output)
        output.close()
        edits = json.loads((ROOT / 'expected.json').read_text())['edits']
        for edit in edits:
            h = History(destination, read_only=True, edit=edit['id'])
            try:
                result['edits'].append({'id': edit['id'], 'windows': [
                    {'first': first,
                     'samples': mixer.mix(h.state, store, first, count).tolist()}
                    for first, count in windows]})
            finally:
                h.close()
    return result


if __name__ == '__main__':
    (ROOT / 'audio.json').write_text(json.dumps(expected_audio(), indent=2) + '\n')
