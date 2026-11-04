"""Optional MCP tools for local, catalog-driven Kuulas automation.

The data and editing surface is ``Session`` plus ``command_catalog``.  The
official MCP SDK is imported only by :func:`serve`, so the editor and HTTP API
do not acquire an MCP dependency unless the optional ``agent`` extra is used.
"""

from __future__ import annotations

import argparse
from importlib import import_module
from pathlib import Path
from typing import Any

from . import colab_signin, command_catalog, messages
from .session import Session

TOOL_NAMES = (
    "project_summary",
    "list_media",
    "read_transcript",
    "list_jobs",
    "list_commands",
    "list_candidates",
    "preview_candidate",
    "transcribe_media",
    "call_command",
    "apply_candidate",
)


class AgentPermissionError(messages.KuulasError, PermissionError):
    """A translated permission failure exposed through the MCP API."""


class AgentValueError(messages.KuulasError, ValueError):
    """A translated invalid-argument failure exposed through the MCP API."""


class AgentTools:
    """Small testable façade over a project session.

    MCP starts read-only.  ``allow_edits`` is an explicit process-level opt-in;
    each write tool also requires ``confirm=True`` so an agent cannot mutate a
    project merely by discovering a tool.
    """

    def __init__(self, session: Session, *, allow_edits: bool = False):
        self.session = session
        self.allow_edits = allow_edits

    def _require_write(self, confirm: bool) -> None:
        if not self.allow_edits:
            raise AgentPermissionError("error.agent.edits_disabled")
        if self.session.read_only:
            host = (self.session.package.locked_by or {}).get("host", "?")
            raise AgentPermissionError("error.history.read_only", host=host)
        if not confirm:
            raise AgentPermissionError("error.agent.confirm_required")

    def project_summary(self) -> dict[str, Any]:
        project = self.session.state
        return {
            "name": Path(self.session.package.path).stem,
            "rate": project.rate,
            "duration_frames": project.length,
            "media_count": len(project.media),
            "track_count": len(project.tracks),
            "read_only": bool(self.session.read_only),
        }

    def list_media(self) -> list[dict[str, Any]]:
        return self.session.state.to_dict().get("media", [])

    def transcript(self) -> dict[str, Any]:
        return {"words": self.session.heard_words(),
                "transcribed_media": self.session.transcribed_media()}

    def jobs(self) -> list[dict[str, Any]]:
        return self.session.background_jobs()

    @staticmethod
    def list_commands() -> list[dict[str, Any]]:
        return command_catalog.catalog()

    def candidates(self, state: str | None = None) -> dict[str, Any]:
        return self.session.candidates(state)

    def preview_candidate(self, candidate_id: str, mode: str = "soft",
                          tracks: list[str] | None = None) -> dict[str, Any]:
        return self.session.candidate_preview(candidate_id, mode, tracks)

    def transcribe_media(self, media_ids: list[str], *, backend: str = "local",
                         model: str | None = None, language: str | None = None,
                         local_engine: str = "whisper", force: bool = False,
                         allow_low_memory: bool = False,
                         confirm: bool = False) -> dict[str, Any]:
        self._require_write(confirm)
        if not media_ids:
            raise AgentValueError("error.agent.empty_media")
        if backend == "colab" and not colab_signin.signed_in():
            raise AgentPermissionError("error.colab.not_signed_in")
        job_ids = self.session.transcribe(
            media_ids, model=model, language=language, backend=backend,
            force=force, allow_low_memory=allow_low_memory,
            local_engine=local_engine,
        )
        return {"jobs": job_ids}

    def call_command(self, name: str, args: dict[str, Any] | None = None, *,
                     confirm: bool = False) -> dict[str, Any]:
        self._require_write(confirm)
        args = args or {}
        entry = next((item for item in command_catalog.catalog()
                      if item["name"] == name), None)
        if entry is None:
            raise AgentValueError("error.agent.unknown_command", name=name)
        if entry["via"] == "/api/edit":
            self.session.edit(name, args)
        else:
            self.session.command(name, args)
        return {"ok": True, "name": name, "undo_step": entry["undo_step"]}

    def apply_candidate(self, candidate_id: str, *, mode: str = "soft",
                        tracks: list[str] | None = None,
                        confirm: bool = False) -> dict[str, Any]:
        self._require_write(confirm)
        return self.session.candidate_apply(candidate_id, mode, tracks)


def create_mcp_server(session: Session, *, allow_edits: bool = False):
    """Build the MCP server with a stable set of named tools."""
    try:
        fast_mcp = import_module("mcp.server.fastmcp").FastMCP
    except ImportError as error:
        raise messages.KuulasError("error.agent.missing_extra") from error

    tools = AgentTools(session, allow_edits=allow_edits)
    server = fast_mcp("Kuulas")

    @server.tool()
    def project_summary() -> dict[str, Any]:
        """Return project name, duration, track/media counts, and lock state."""
        return tools.project_summary()

    @server.tool()
    def list_media() -> list[dict[str, Any]]:
        """List media ids, names, lengths, and project metadata."""
        return tools.list_media()

    @server.tool()
    def read_transcript() -> dict[str, Any]:
        """Read transcript words and ids of media with transcripts; times are frames."""
        return tools.transcript()

    @server.tool()
    def list_jobs() -> list[dict[str, Any]]:
        """List transcription and analysis jobs, including progress and failures."""
        return tools.jobs()

    @server.tool()
    def list_commands() -> list[dict[str, Any]]:
        """List the available Kuulas commands and their argument schemas."""
        return tools.list_commands()

    @server.tool()
    def list_candidates(state: str | None = None) -> dict[str, Any]:
        """List cut candidates, optionally filtered by state."""
        return tools.candidates(state)

    @server.tool()
    def preview_candidate(candidate_id: str, mode: str = "soft",
                          tracks: list[str] | None = None) -> dict[str, Any]:
        """Preview candidate edits without changing the session."""
        return tools.preview_candidate(candidate_id, mode, tracks)

    @server.tool()
    def transcribe_media(media_ids: list[str], backend: str = "local",
                         model: str | None = None, language: str | None = None,
                         local_engine: str = "whisper", force: bool = False,
                         allow_low_memory: bool = False,
                         confirm: bool = False) -> dict[str, Any]:
        """Start local Whisper/Orukeet or Colab transcription; returns job ids."""
        return tools.transcribe_media(
            media_ids, backend=backend, model=model, language=language,
            local_engine=local_engine, force=force,
            allow_low_memory=allow_low_memory, confirm=confirm,
        )

    @server.tool()
    def call_command(name: str, args: dict[str, Any] | None = None,
                     confirm: bool = False) -> dict[str, Any]:
        """Run a catalogued Kuulas command; pass confirm=true to authorize the edit."""
        return tools.call_command(name, args, confirm=confirm)

    @server.tool()
    def apply_candidate(candidate_id: str, mode: str = "soft",
                        tracks: list[str] | None = None,
                        confirm: bool = False) -> dict[str, Any]:
        """Apply a candidate as a soft mute or ripple cut after explicit confirmation."""
        return tools.apply_candidate(candidate_id, mode=mode, tracks=tracks,
                                     confirm=confirm)

    return server


def serve(project: str | Path, *, allow_edits: bool = False) -> None:
    session = Session(project)
    try:
        create_mcp_server(session, allow_edits=allow_edits).run(transport="stdio")
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Expose a Kuulas project to an MCP agent.")
    parser.add_argument("project", help="path to a .kuulas project")
    parser.add_argument("--allow-edits", action="store_true",
                        help="allow confirmed changes and transcription jobs")
    args = parser.parse_args()
    serve(args.project, allow_edits=args.allow_edits)


if __name__ == "__main__":
    main()
