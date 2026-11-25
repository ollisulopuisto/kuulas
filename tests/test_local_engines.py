"""Which local engine a transcription uses when nobody said: decided in one place.

Two different questions, each with one answer in ``kuulas.local_engines``:
a new request that names no engine, and a job file written before the engine selector
existed (it has no ``local_engine``)."""

import inspect
import json

from test_transcribe_worker import WORDS

from kuulas import bgjobs, colab_transcribe, local_engines, mcp_server, server, session
from kuulas.transcribe_worker import run_job


def _default(function):
    return inspect.signature(function).parameters["local_engine"].default


def test_the_two_defaults_are_named_and_are_valid_engines():
    assert local_engines.DEFAULT in local_engines.ENGINES
    assert local_engines.LEGACY in local_engines.ENGINES
    assert set(local_engines.ENGINES) == {"whisper", "orukeet"}


def test_every_entry_point_defaults_to_the_one_named_default():
    pieces = {
        "server.TranscribeBody":
            server.TranscribeBody.model_fields["local_engine"].default,
        "Session.transcribe": _default(session.Session.transcribe),
        "mcp transcribe_media": _default(mcp_server.AgentTools.transcribe_media),
    }
    assert pieces == dict.fromkeys(pieces, local_engines.DEFAULT)


def test_a_job_file_without_an_engine_means_the_legacy_one_and_an_explicit_one_wins():
    assert local_engines.of_job({}) == local_engines.LEGACY
    assert local_engines.of_job({"local_engine": None}) == local_engines.LEGACY
    assert local_engines.of_job({"local_engine": "whisper"}) == "whisper"
    assert local_engines.of_job({"local_engine": "orukeet"}) == "orukeet"


def test_the_worker_runs_a_job_without_an_engine_as_the_legacy_engine(tmp_path):
    folder = tmp_path / "P.kuulas"
    items = [{"id": "m0", "name": "a.wav", "path": str(tmp_path / "a.wav")}]
    job_id = bgjobs.create_job(
        folder, backend="local", items=items, previous={"m0": None}, names=["a.wav"],
        model="small", language="fi", settings=None)
    path = bgjobs.job_file(folder, job_id)
    assert json.loads(path.read_text()).get("local_engine") is None
    calls = []

    def fake(name):
        def engine(path_, model=None, language=None, progress=None, **kwargs):
            calls.append(name)
            progress(1.0)
            return WORDS
        return engine

    # `local` is the Orukeet engine of the worker, `whisper` the Whisper one.
    assert run_job(path, local=fake("orukeet"), whisper=fake("whisper")) == "completed"
    assert set(calls) == {local_engines.LEGACY}
    result = colab_transcribe.read_words_json(bgjobs.result_file(folder, job_id, "m0"))
    assert result["engine"]["tool"] == local_engines.LEGACY
