"""The native reader's checked fixture must match real Kuulas, not NHSX."""
import importlib.util
import json
import shutil
from pathlib import Path

from kuulas.history import History
from kuulas.package import READER

FIXTURE = Path(__file__).resolve().parents[1] / 'viewer' / 'Conformance'


def test_native_reader_fixture_matches_current_python_history(tmp_path):
    source = tmp_path / 'Session.kuulas'
    shutil.copytree(FIXTURE / 'Session.kuulas', source)
    expected = json.loads((FIXTURE / 'expected.json').read_text())
    manifest = json.loads((FIXTURE / 'Session.kuulas' / 'manifest.json').read_text())
    assert manifest['min_reader'] <= READER
    for edit in expected['edits']:
        history = History(source / 'project.sqlite',
                          read_only=True, edit=edit['id'])
        try:
            assert history.head == edit['head']
            assert json.loads(history.state.to_json()) == edit['project']
        finally:
            history.close()


def test_native_audio_golden_matches_current_python_mixer():
    path = FIXTURE.parent / 'Tools' / 'make_audio_conformance.py'
    spec = importlib.util.spec_from_file_location('audio_conformance', path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    expected = json.loads((FIXTURE / 'audio.json').read_text())
    assert tool.expected_audio() == expected
