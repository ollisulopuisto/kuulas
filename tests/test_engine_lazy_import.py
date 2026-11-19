"""`kuulas.engine` must import without a working audio server (2026-11-19):
the ubuntu CI image lost its PulseAudio server and `import sounddevice` alone
killed collection for the whole shard. The engine imports it lazily now, so a
missing server only fails the tests that actually open a device.
"""

import os
import subprocess
import sys
import types
from pathlib import Path

from kuulas import engine

SRC = Path(__file__).resolve().parent.parent / "src"


def test_engine_imports_when_sounddevice_cannot_initialize(tmp_path):
    stub = tmp_path / "sounddevice.py"
    stub.write_text("raise OSError('PortAudio: no server')\n")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path), str(SRC)])}
    result = subprocess.run(
        [sys.executable, "-c", "import kuulas.engine; print('imported')"],
        capture_output=True,
        check=False,
        text=True,
        env=env,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "imported" in result.stdout


def test_attribute_writes_reach_the_real_module(monkeypatch):
    """Tests and callers patch `engine.sd.<name>`; a read-only proxy would keep
    the write on the wrapper itself and the engine would go on using the
    unpatched value (review-bot finding on PR #242)."""
    fake = types.ModuleType("sounddevice")
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    proxy = engine._LazySounddevice()
    proxy.default_device = 3
    assert fake.default_device == 3


def test_playback_import_failure_is_localized_and_can_recover(monkeypatch):
    import builtins  # noqa: PLC0415 - fault injection scoped to this test

    import pytest  # noqa: PLC0415
    from test_engine import Clock, install_rig, make, sd  # noqa: PLC0415

    rig = install_rig(monkeypatch)
    player, _, _ = make(rig, Clock())
    proxy = engine._LazySounddevice()
    monkeypatch.setattr(engine, "sd", proxy)
    real_import = builtins.__import__
    attempts = []

    def fail_audio(name, *args, **kwargs):
        if name == "sounddevice":
            attempts.append(name)
            raise OSError("no audio server")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_audio)
    with pytest.raises(engine.EngineError) as error:
        player.play(0)
    assert error.value.key == "error.engine.no_device"
    assert len(attempts) == 1
    assert not player.is_playing
    monkeypatch.setattr(builtins, "__import__", real_import)
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    player.play(0)
    assert player.is_playing
    player.close()
