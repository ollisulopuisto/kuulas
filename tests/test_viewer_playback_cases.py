"""The extended native playback golden comes from the real Python mix path."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'viewer'


def test_extended_playback_golden_matches_real_mixer():
    spec = importlib.util.spec_from_file_location(
        'playback_cases', ROOT / 'Tools/make_playback_cases.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.expected() == json.loads(
        (ROOT / 'Conformance/playback-cases.json').read_text())
