"""The desktop workflow also starts the engine, so it needs CI virtual audio."""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/desktop-smoke.yml"


def test_desktop_smoke_starts_virtual_audio_before_loading_the_engine():
    workflow = WORKFLOW.read_text()
    install = workflow.index("ffmpeg libportaudio2 libsndfile1 pulseaudio")
    start = workflow.index("pulseaudio --start --exit-idle-time=-1")
    sink = workflow.index("pactl set-default-sink ci_null_sink")
    source = workflow.index("pactl set-default-source ci_null_source")
    tests = workflow.index("uv run pytest -q tests/test_desktop.py")
    assert install < start < sink < source < tests
    assert "pactl load-module module-null-sink sink_name=ci_null_sink" in workflow
    assert "pactl load-module module-null-source source_name=ci_null_source" in workflow
