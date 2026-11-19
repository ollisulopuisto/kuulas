"""The CI audio contract (2026-11-19): ubuntu runners start a PulseAudio daemon
with a null sink and source, so the real audio path runs against a virtual
device. If the runner image drops the server again, this fails loudly instead
of every audio test erroring at collection. It lives in tests/hardware (ground
rule 4: device tests are run explicitly, never skipped) and the ubuntu CI jobs
invoke it by path after starting the daemon.
"""

import sounddevice as sd


def test_the_ci_audio_server_is_up_with_a_default_device():
    devices = sd.query_devices()
    assert len(devices) > 0, "CI runner has no audio devices: PulseAudio down?"
    # A default device in each direction (the null sink and source in CI).
    sd.query_devices(kind="output")
    sd.query_devices(kind="input")
    sd.check_output_settings()
    sd.check_input_settings()
