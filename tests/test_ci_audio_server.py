"""The CI audio contract (2026-11-19): ubuntu runners start a PulseAudio daemon
with a null sink and source, so the real audio path runs against a virtual
device. If the runner image drops the server again, this test fails loudly at
the top of the shard instead of every audio test erroring at collection.
Locally (a machine with real audio or none) it skips.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CI") != "true", reason="the daemon contract binds CI runners"
)


def test_the_ci_audio_server_is_up_with_a_default_device():
    import sounddevice as sd  # noqa: PLC0415 - collection must not need a server

    devices = sd.query_devices()
    assert len(devices) > 0, "CI runner has no audio devices: PulseAudio down?"
    # A default device in each direction (the null sink and source in CI).
    sd.query_devices(kind="output")
    sd.query_devices(kind="input")
    sd.check_output_settings()
    sd.check_input_settings()
