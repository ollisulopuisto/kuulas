"""Agent-facing MCP tools are discoverable and keep writes behind explicit gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuulas import mcp_server
from kuulas.mcp_server import TOOL_NAMES, AgentTools


class FakeState:
    def to_dict(self):
        return {
            "name": "Episode",
            "rate": 48000,
            "duration_frames": 200,
            "media": [{"id": "m1", "name": "olli.wav", "frames": 100}],
            "tracks": [{"id": "t1", "name": "Olli", "clips": []}],
        }


class FakeProject:
    rate = 48000
    length = 200
    media = (object(),)
    tracks = (object(),)

    def to_dict(self):
        return FakeState().to_dict()


class FakeSession:
    state = FakeProject()
    read_only = False
    package = type("Package", (), {"path": "Episode.kuulas"})()

    def __init__(self):
        self.transcribe_args = None
        self.command_args = None
        self.edit_args = None

    def heard_words(self):
        return [{"media": "m1", "w": "um", "s": 0, "e": 5}]

    def transcribed_media(self):
        return ["m1"]

    def background_jobs(self):
        return [{"id": "j1", "state": "running", "progress": 0.4}]

    def candidates(self, state=None):
        return {"candidates": [], "summary": {"open": 0}}

    def candidate_preview(self, candidate_id, mode="soft", tracks=None):
        return {"id": candidate_id, "mode": mode, "tracks": tracks or []}

    def transcribe(self, media_ids, model=None, language=None, backend="local",
                   force=False, allow_low_memory=False, local_engine="whisper"):
        self.transcribe_args = (media_ids, model, language, backend, force, local_engine)
        return ["j2"]

    def command(self, name, args):
        self.command_args = (name, args)

    def edit(self, name, args, label=None):
        self.edit_args = (name, args, label)

    def candidate_apply(self, candidate_id, mode="soft", tracks=None):
        self.command_args = ("candidate_apply", {"id": candidate_id,
                                                  "mode": mode, "tracks": tracks})
        return {"mode": mode, "spans": [[1, 2]], "tracks": tracks or ["t1"]}


def test_read_tools_summarize_project_transcript_jobs_and_commands():
    session = FakeSession()
    tools = AgentTools(session, allow_edits=False)

    summary = tools.project_summary()
    assert summary["media_count"] == 1
    assert summary["track_count"] == 1
    assert summary["duration_frames"] == 200
    assert tools.list_media()[0]["id"] == "m1"
    assert tools.transcript()["words"] == session.heard_words()
    assert tools.jobs() == session.background_jobs()
    assert {entry["name"] for entry in tools.list_commands()} >= {
        "candidates_detect", "candidate_apply", "cut_words",
    }


def test_documentation_lists_every_mcp_tool():
    documentation = Path(__file__).parents[1].joinpath("docs/SCRIPTING.md").read_text()
    assert all(f"`{name}`" in documentation for name in TOOL_NAMES)


def test_transcription_is_disabled_by_default():
    tools = AgentTools(FakeSession(), allow_edits=False)
    with pytest.raises(PermissionError, match="read-only"):
        tools.transcribe_media(["m1"])


def test_transcription_is_explicit_and_reports_async_jobs():
    session = FakeSession()
    tools = AgentTools(session, allow_edits=True)

    result = tools.transcribe_media(["m1"], backend="colab", model="large-v3-turbo",
                                    language="fi", local_engine="whisper", confirm=True)

    assert result == {"jobs": ["j2"]}
    assert session.transcribe_args == (
        ["m1"], "large-v3-turbo", "fi", "colab", False, "whisper")


def test_colab_transcription_requires_sign_in(monkeypatch):
    monkeypatch.setattr(mcp_server.colab_signin, "signed_in", lambda: False)
    tools = AgentTools(FakeSession(), allow_edits=True)

    with pytest.raises(PermissionError, match="Google"):
        tools.transcribe_media(["m1"], backend="colab", confirm=True)


def test_locked_project_rejects_confirmed_edits():
    session = FakeSession()
    session.read_only = True
    session.package.locked_by = {"host": "another-machine"}
    tools = AgentTools(session, allow_edits=True)

    with pytest.raises(PermissionError, match="another-machine"):
        tools.call_command("candidates_detect", {}, confirm=True)


def test_transcription_rejects_empty_media_list():
    tools = AgentTools(FakeSession(), allow_edits=True)

    with pytest.raises(ValueError, match="at least one"):
        tools.transcribe_media([], confirm=True)


def test_generic_command_requires_launch_opt_in_and_per_call_confirmation():
    session = FakeSession()
    readonly = AgentTools(session, allow_edits=False)
    with pytest.raises(PermissionError, match="read-only"):
        readonly.call_command("candidates_detect", {})

    writable = AgentTools(session, allow_edits=True)
    with pytest.raises(PermissionError, match="confirm=true"):
        writable.call_command("candidates_detect", {})

    result = writable.call_command("candidates_detect", {}, confirm=True)
    assert result["ok"] is True
    assert session.command_args == ("candidates_detect", {})

    with pytest.raises(ValueError, match="Unknown Kuulas command"):
        writable.call_command("not-a-kuulas-command", {}, confirm=True)


def test_candidate_preview_is_read_only_and_apply_requires_confirmation():
    session = FakeSession()
    tools = AgentTools(session, allow_edits=True)
    assert tools.preview_candidate("c1")["mode"] == "soft"

    with pytest.raises(PermissionError, match="confirm=true"):
        tools.apply_candidate("c1")

    result = tools.apply_candidate("c1", confirm=True)
    assert result == {"mode": "soft", "spans": [[1, 2]], "tracks": ["t1"]}
    assert session.command_args[0] == "candidate_apply"
