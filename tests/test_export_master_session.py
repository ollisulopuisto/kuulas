"""Candidate mastering crosses the public Session export, writer and rollback.

The production default stays legacy; no monkeypatched DSP/sink stands in for
this whole-app export boundary. This is separate from API-level parity tests.
"""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import export
from kuulas.session import Session

RATE = 48000


def test_session_streaming_wav_matches_legacy_file_and_global_report(
        tmp_path, monkeypatch):
    t = np.arange(RATE * 3 + 13) / RATE
    wave = (.1 * np.sin(2 * np.pi * 137 * t)
            + .05 * np.sin(2 * np.pi * 911 * t)).astype(np.float32)
    input_path = tmp_path / 'stereo.wav'
    sf.write(input_path, np.column_stack([wave, wave * .6]), RATE, subtype='FLOAT')
    session = Session(tmp_path / 'session.kuulas')
    try:
        session.import_media([str(input_path)])
        args = {'kind': 'mix', 'format': 'wav', 'bit_depth': 32,
                'master_lufs': -16.0}
        monkeypatch.setattr(export, 'STREAM_MASTERING_ENABLED', False)
        legacy = session.export({**args, 'folder': str(tmp_path / 'legacy')})
        monkeypatch.setattr(export, 'STREAM_MASTERING_ENABLED', True)
        candidate = session.export({**args, 'folder': str(tmp_path / 'candidate')})
        old, old_rate = sf.read(legacy['path'], dtype='float32', always_2d=True)
        new, new_rate = sf.read(candidate['path'], dtype='float32', always_2d=True)
        assert old_rate == new_rate == RATE
        np.testing.assert_allclose(new, old, rtol=0, atol=1e-7)
        assert candidate['master'] == legacy['master']
        assert candidate['master']['reached']
        assert candidate['master']['lufs'] == pytest.approx(-16, abs=.5)
        assert not list(tmp_path.rglob('*.partial'))
        assert Path(candidate['path']).is_file()
    finally:
        session.close()
