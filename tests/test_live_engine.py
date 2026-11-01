"""The warm Orukeet engine factory: receipt reuse, worker transport, lifecycle."""

from __future__ import annotations

import json
import sys
import textwrap

import pytest

from kuulas import live_engine
from kuulas.live_engine import LiveEngineProcess, warm_engine_factory


@pytest.fixture
def receipt(tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"gguf")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    return {"model": str(model), "runtime": str(runtime), "device": "cpu"}


class TestReceipt:
    def test_reads_the_existing_installation(self, tmp_path, receipt):
        path = tmp_path / "installation.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        assert live_engine.read_receipt(path) == receipt

    def test_missing_or_broken_receipt_means_no_live_transcript(self, tmp_path,
                                                                receipt):
        assert live_engine.read_receipt(tmp_path / "none.json") is None
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert live_engine.read_receipt(bad) is None
        missing = tmp_path / "missing.json"
        missing.write_text(json.dumps({**receipt, "model": str(tmp_path / "x")}),
                           encoding="utf-8")
        assert live_engine.read_receipt(missing) is None  # model file gone

    def test_env_override_points_elsewhere(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ORUKEET_INSTALLATION", str(tmp_path / "elsewhere.json"))
        assert live_engine.receipt_path() == tmp_path / "elsewhere.json"


FAKE_WORKER = textwrap.dedent("""
    import array, json, sys, time
    for line in sys.stdin:
        req = json.loads(line)
        op = req.get("op")
        if op == "load":
            resp = {"id": req["id"], "result": {"device": req["device"]}}
        elif op == "transcribe":
            samples = array.array("f")
            with open(req["audio_path"], "rb") as fh:
                samples.frombytes(fh.read())
            resp = {"id": req["id"], "result": {"words": [
                {"word": "chunk", "start": 0.0,
                 "end": len(samples) / req["rate"]}]}}
        elif op == "boom":
            sys.exit(3)
        elif op == "sleep":
            time.sleep(5)
            resp = {"id": req["id"], "result": {}}
        else:
            resp = {"id": req.get("id"), "error": "unknown op"}
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
""")


@pytest.fixture
def fake_command(tmp_path):
    script = tmp_path / "fake_worker.py"
    script.write_text(FAKE_WORKER, encoding="utf-8")
    return [sys.executable, "-u", str(script)]


class TestLiveEngineProcess:
    def test_load_then_many_transcriptions_one_process(self, fake_command,
                                                       tmp_path):
        process = LiveEngineProcess(fake_command)
        try:
            assert process.request("load", model_path="m", runtime="r",
                                   device="cpu") == {"device": "cpu"}
            audio_path = tmp_path / "chunk.f32"
            audio_path.write_bytes(b"\x00" * 400)
            out = process.request("transcribe", audio_path=str(audio_path),
                                  rate=16000)
            assert out["words"][0]["word"] == "chunk"
        finally:
            process.close()
        assert process.process.poll() is not None  # the worker is gone

    def test_worker_death_is_one_clear_error(self, fake_command):
        process = LiveEngineProcess(fake_command)
        process.request("load", model_path="m", runtime="r", device="cpu")
        with pytest.raises(RuntimeError, match="stopped"):
            process.request("boom")

    def test_timeout_closes_the_worker(self, fake_command):
        process = LiveEngineProcess(fake_command)
        process.request("load", model_path="m", runtime="r", device="cpu")
        with pytest.raises(RuntimeError, match=r"error\.live_engine\.timeout"):
            process.request("sleep", timeout=0.3)
        assert process.process.poll() is not None
        with pytest.raises(RuntimeError, match="closed"):
            process.request("load", model_path="m", runtime="r", device="cpu")


class FakeSpawn:
    """A scripted stand-in for the worker process (no subprocess)."""

    def __init__(self):
        self.requests = []
        self.closed = False

    def request(self, op, *, timeout=180., **payload):
        self.requests.append((op, payload))
        if op == "load":
            return {"device": payload["device"]}
        return {"words": [{"word": "sana", "start": 0.0, "end": 0.5}]}

    def close(self):
        self.closed = True


class TestWarmEngineFactory:
    def test_loads_once_and_transcribes_chunks(self, receipt):
        spawn = FakeSpawn()
        engine = warm_engine_factory(receipt, spawn=lambda: spawn)
        assert spawn.requests[0] == ("load", {
            "model_path": receipt["model"], "runtime": receipt["runtime"],
            "device": "cpu"})
        words = engine([0.0] * 24000, 48000)
        assert words == [{"word": "sana", "start": 0.0, "end": 0.5}]
        op, payload = spawn.requests[1]
        assert op == "transcribe"
        assert payload["rate"] == 48000
        engine.close()
        assert spawn.closed

    def test_no_installation_raises_before_any_work(self, tmp_path):
        with pytest.raises(RuntimeError, match="no_installation"):
            warm_engine_factory(receipt=None)
        # read_receipt() on an empty default location must not raise either
        assert live_engine.factory_or_none(receipt=None) is None

    def test_factory_or_none_wraps_a_valid_receipt(self, receipt):
        factory = live_engine.factory_or_none(receipt=receipt, spawn=FakeSpawn)
        assert factory is not None
        engine = factory()
        assert engine([0.0], 16000)[0]["word"] == "sana"
        engine.close()
