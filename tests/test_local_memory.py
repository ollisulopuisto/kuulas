"""Eligibility policy boundaries and refusal before model/tool access."""
from types import SimpleNamespace

import pytest

from kuulas import local_memory, local_models, transcribe


@pytest.mark.parametrize(
    ("memory", "expected"),
    [
        (8 * 1024**3, False),
        (16 * 1024**3 - 1, False),
        (16 * 1024**3, True),
        (32 * 1024**3, True),
        (None, False),
    ],
)
def test_boundary(monkeypatch, memory, expected):
    monkeypatch.setattr(local_memory, "physical_memory", lambda: memory)
    assert local_memory.eligible() is expected
    assert local_models.status()["eligible"] is expected


@pytest.mark.parametrize("memory", [None, 8 * 1024**3])
def test_local_refuses_before_model_or_process(monkeypatch, memory):
    monkeypatch.setattr(local_memory, "physical_memory", lambda: memory)
    monkeypatch.setattr(
        local_models, "model_path", lambda: pytest.fail("model inspected")
    )
    with pytest.raises(transcribe.TranscribeError, match=None) as error:
        transcribe.local("not-present.wav")
    assert error.value.key == "error.orukeet.memory"


def test_detection_failure(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(local_memory.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        local_memory.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )
    assert local_memory.physical_memory() is None


def test_detection_uses_total_physical_memory(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(local_memory.platform, "system", lambda: "Darwin")

    def run(argv, **kwargs):
        assert argv == ["/usr/sbin/sysctl", "-n", "hw.memsize"]
        return SimpleNamespace(stdout=str(16 * 1024**3))

    monkeypatch.setattr(local_memory.subprocess, "run", run)
    assert local_memory.physical_memory() == 16 * 1024**3
