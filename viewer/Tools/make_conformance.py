"""Explicitly regenerate the checked native-reader fixture; review every diff.

Run with PYTHONPATH=src from the repository root. Only generated public synthetic
media and model data belongs in this fixture. Never use a real project here.
"""
import json
import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf

from kuulas import ops, package
from kuulas.history import History
from kuulas.model import Bus, Clip, Marker, Track

ROOT = Path(__file__).resolve().parents[1] / 'Conformance'
TARGET = ROOT / 'Session.kuulas'


def main():
    if TARGET.exists():
        shutil.rmtree(TARGET)
    p = package.create(TARGET)
    source = TARGET / 'recordings' / 'tone.wav'
    sf.write(source, np.sin(np.arange(4800) * 0.02).astype('float32'), 48000,
             subtype='PCM_16')
    media = p.store.import_file(source, copy=False)
    clip = Clip('clip-one', media.id, 2400, 120, 2400, gain_db=-3,
                pan=-0.4, fade_in=240, fade_out=120,
                envelope=((120, -2.0), (2520, 0.0)),
                auto_silence=((1000, 1100),))
    track = Track('track-one', 'Host', bus='bus-one', clips=(clip,),
                  gain_db=-2, pan=0.1, solo=True, mute=True,
                  automation=((0, 0.0), (4800, -3.0)), gate=((3000, 3200),))
    state = replace(p.history.state, tracks=(track,),
                    buses=(Bus('bus-one', 'Voices', gain_db=-1, pan=-0.2),),
                    markers=(Marker('marker-one', 'Start', 2400),), master_gain_db=-4)
    p.history.commit('Synthetic complex mix', state)
    p.history.create_edit('Short alternative', replace(state, tracks=()))
    archived = p.history.create_edit('Archived draft')
    p.history.db.execute('update edits set archived=1 where id=?', (archived,))
    # The head is intentionally NOT the newest node. A reader taking MAX(id)
    # would show the abandoned -22 dB state rather than this -4 dB one.
    p.history.commit('Abandoned master', ops.set_master(state, -22))
    p.history.undo()
    expected = {'edits': []}
    for row in p.history.edits():
        h = History(p.db_path, read_only=True, edit=row['id'])
        expected['edits'].append({**row, 'project': h.state.to_dict()})
        h.close()
    p.close()
    # A linked file in a moved package must resolve by package-relative path.
    # The nonexistent absolute path is deliberate and independent of build host.
    db = sqlite3.connect(TARGET / 'project.sqlite')
    db.execute("update media set linked_path='/missing/original/tone.wav'")
    db.commit()
    db.execute('pragma wal_checkpoint(truncate)')
    db.close()
    for name in ('backups', 'caches', 'locks', 'media'):
        shutil.rmtree(TARGET / name)
    (ROOT / 'expected.json').write_text(json.dumps(expected, indent=2) + '\n')


if __name__ == '__main__':
    main()
