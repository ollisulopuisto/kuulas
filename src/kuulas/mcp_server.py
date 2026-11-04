"""Model Context Protocol (MCP) server for kuulas (WP53).

Exposes project inspection and editing capabilities to LLM agents (Claude Desktop,
Cursor, Claude Code, etc.) over JSON-RPC 2.0 stdio.

Safety: Read-only by default. When ``allow_edits`` is False, mutations (edits,
commands, undo, redo) are refused with an explicit error.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, TextIO

from . import command_catalog, ctl_discovery
from .ctl import call_server
from .messages import KuulasError, t
from .session import Session

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "kuulas"
SERVER_VERSION = "1.0.0"


class McpRpcError(KuulasError):
    """An MCP error whose message is translated via KuulasError."""

    def __init__(self, key: str, /, code: int = -32000, **params: Any) -> None:
        super().__init__(key, **params)
        self.code = code
        self.message = t(key, **params)


class McpServer:
    """Handles JSON-RPC 2.0 communication for the MCP protocol."""

    def __init__(
        self,
        project_folder: str | os.PathLike[str],
        *,
        allow_edits: bool = False,
    ):
        self.project_folder = str(project_folder)
        self.allow_edits = allow_edits
        self._session: Session | None = None

    def _get_live_info(self) -> dict[str, Any] | None:
        """Return discovery dict if live instance exists and is running."""
        info = ctl_discovery.read(self.project_folder)
        if info and ctl_discovery.is_alive(info):
            return info
        return None

    def _get_headless_session(self) -> Session:
        """Return an open headless session (cached)."""
        if self._session is None:
            self._session = Session(self.project_folder)
        return self._session

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    # -- Internal Query / Action Dispatch ------------------------------------

    def get_state(self) -> dict[str, Any]:
        live = self._get_live_info()
        if live:
            return call_server(live["port"], live["token"], "/api/state")
        s = self._get_headless_session()
        return {
            "project": s.state.to_dict(),
            "head": s.history.head,
            "can_undo": s.history.can_undo,
            "can_redo": s.history.can_redo,
            "missing": s.store.missing(),
        }

    def get_words(self) -> list[dict[str, Any]]:
        live = self._get_live_info()
        if live:
            res = call_server(live["port"], live["token"], "/api/words")
            return res.get("words", [])
        return self._get_headless_session().heard_words()

    def search_transcript(self, query: str) -> list[dict[str, Any]]:
        query_lower = query.lower()
        words = self.get_words()
        hits = []
        for idx, item in enumerate(words):
            word_text = item.get("w", "")
            if query_lower in word_text.lower():
                hits.append({"index": idx, **item})
        return hits

    def list_commands(self) -> list[dict[str, Any]]:
        return command_catalog.catalog()

    def execute_edit(self, op: str, args: dict[str, Any]) -> dict[str, Any]:
        if not self.allow_edits:
            raise McpRpcError("error.mcp.edits_disabled", code=-32000)
        live = self._get_live_info()
        if live:
            payload = {"op": op, "args": args}
            return call_server(
                live["port"], live["token"], "/api/edit", method="POST", body=payload
            )
        s = self._get_headless_session()
        s.edit(op, args)
        return {"head": s.history.head, "can_undo": s.history.can_undo}

    def execute_command(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if not self.allow_edits:
            raise McpRpcError("error.mcp.commands_disabled", code=-32000)
        live = self._get_live_info()
        if live:
            payload = {"name": name, "args": args}
            return call_server(
                live["port"], live["token"], "/api/command", method="POST", body=payload
            )
        s = self._get_headless_session()
        s.command(name, args)
        return {"head": s.history.head, "can_undo": s.history.can_undo}

    def undo(self) -> dict[str, Any]:
        if not self.allow_edits:
            raise McpRpcError("error.mcp.undo_disabled", code=-32000)
        live = self._get_live_info()
        if live:
            return call_server(live["port"], live["token"], "/api/undo", method="POST")
        s = self._get_headless_session()
        info = s.undo()
        return {"head": s.history.head, "info": str(info)}

    def redo(self) -> dict[str, Any]:
        if not self.allow_edits:
            raise McpRpcError("error.mcp.redo_disabled", code=-32000)
        live = self._get_live_info()
        if live:
            return call_server(live["port"], live["token"], "/api/redo", method="POST")
        s = self._get_headless_session()
        info = s.redo()
        return {"head": s.history.head, "info": str(info)}

    # -- Tool / Resource / Prompt Definitions --------------------------------

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "get_project_state",
                "description": "Get project state (tracks, clips, buses, head).",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_heard_words",
                "description": "Get transcript words currently heard in edit.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "search_transcript",
                "description": "Search for words in the heard transcript.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search text"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "list_commands",
                "description": "List all editing and session commands.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "execute_edit",
                "description": "Execute an edit operation committing one undo step.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "op": {"type": "string", "description": "Edit op name"},
                        "args": {"type": "object", "description": "Edit args"},
                    },
                    "required": ["op"],
                },
            },
            {
                "name": "execute_command",
                "description": "Execute a session command (e.g. cut_words).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Command name"},
                        "args": {"type": "object", "description": "Command args"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "undo",
                "description": "Undo the last edit operation.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "redo",
                "description": "Redo the previously undone edit operation.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]

    def get_resource_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "uri": "kuulas://project/state",
                "name": "Project State",
                "description": "Tracks, buses, clips, and playback settings",
                "mimeType": "application/json",
            },
            {
                "uri": "kuulas://project/words",
                "name": "Heard Words",
                "description": "Transcript words heard in the active edit",
                "mimeType": "application/json",
            },
            {
                "uri": "kuulas://project/commands",
                "name": "Command Catalog",
                "description": "Full catalogue of supported edits and commands",
                "mimeType": "application/json",
            },
        ]

    def get_prompt_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "review_transcript",
                "description": "Review transcript for audio cut suggestions.",
                "arguments": [],
            },
            {
                "name": "summarize_project",
                "description": "Summarize project structure, speakers, timing.",
                "arguments": [],
            },
        ]

    # -- Request Handling ----------------------------------------------------

    def handle_request(self, request_data: Any) -> dict[str, Any] | None:
        """Validate a JSON-RPC request and dispatch it; notifications have no reply."""
        if (
            not isinstance(request_data, dict)
            or request_data.get("jsonrpc") != "2.0"
            or not isinstance(request_data.get("method"), str)
        ):
            request_id = (
                request_data.get("id") if isinstance(request_data, dict) else None
            )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32600, "message": "Invalid Request"},
            }
        is_notification = "id" not in request_data
        response = self._dispatch_request(request_data)
        return None if is_notification else response

    def _dispatch_request(self, request_data: dict[str, Any]) -> dict[str, Any] | None:  # noqa: PLR0911
        msg_id = request_data.get("id")
        method = request_data.get("method")
        params = request_data.get("params") or {}

        if method == "notifications/initialized":
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": self.get_tool_definitions()},
            }

        if method == "tools/call":
            return self._handle_tool_call(msg_id, params)

        if method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"resources": self.get_resource_definitions()},
            }

        if method == "resources/read":
            return self._handle_resource_read(msg_id, params)

        if method == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"prompts": self.get_prompt_definitions()},
            }

        if method == "prompts/get":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": self._get_prompt(params.get("name")),
            }

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _handle_tool_call(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        tool_name = params.get("name")
        args = params.get("arguments") or {}
        try:
            content = self._call_tool(tool_name, args)
            raw = json.dumps(content, indent=2, ensure_ascii=False)
        except McpRpcError as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Error: {e.message}"}],
                },
            }
        except (ValueError, KeyError, OSError, RuntimeError) as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                },
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": raw}]},
            }

    def _handle_resource_read(
        self, msg_id: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        uri = params.get("uri")
        try:
            res_content = self._read_resource(uri)
            text_val = json.dumps(res_content, indent=2, ensure_ascii=False)
        except (ValueError, KeyError, OSError) as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": str(e)},
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "contents": [
                        {"uri": uri, "mimeType": "application/json", "text": text_val}
                    ]
                },
            }

    def _call_tool(self, name: str, args: dict[str, Any]) -> Any:  # noqa: PLR0911
        if name == "get_project_state":
            return self.get_state()
        if name == "get_heard_words":
            return self.get_words()
        if name == "search_transcript":
            return self.search_transcript(args.get("query", ""))
        if name == "list_commands":
            return self.list_commands()
        if name == "execute_edit":
            return self.execute_edit(args.get("op", ""), args.get("args") or {})
        if name == "execute_command":
            return self.execute_command(args.get("name", ""), args.get("args") or {})
        if name == "undo":
            return self.undo()
        if name == "redo":
            return self.redo()
        raise McpRpcError("error.mcp.unknown_tool", code=-32601, name=name)

    def _read_resource(self, uri: str) -> Any:
        if uri == "kuulas://project/state":
            return self.get_state()
        if uri == "kuulas://project/words":
            return self.get_words()
        if uri == "kuulas://project/commands":
            return self.list_commands()
        raise McpRpcError("error.mcp.unknown_resource", code=-32602, uri=uri)

    def _get_prompt(self, name: str) -> dict[str, Any]:
        if name == "review_transcript":
            words = self.get_words()
            sample_words = [w.get("w", "") for w in words[:100]]
            return {
                "description": "Review transcript for editing suggestions",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": (
                                f"Transcript begins ({len(words)} total words):\n"
                                + " ".join(sample_words)
                                + "\n\nReview for fillers, pauses, or cuts."
                            ),
                        },
                    }
                ],
            }
        if name == "summarize_project":
            state = self.get_state()
            tracks = [t.get("name") for t in state.get("project", {}).get("tracks", [])]
            return {
                "description": "Summarize the project",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": (
                                f"Tracks ({len(tracks)}): {', '.join(tracks)}.\n"
                                f"Head: {state.get('head')}.\n"
                                "Summarize project state and pending work."
                            ),
                        },
                    }
                ],
            }
        raise McpRpcError("error.mcp.unknown_prompt", code=-32602, name=name)


def serve_stdio(
    project_folder: str | os.PathLike[str],
    *,
    allow_edits: bool = False,
    in_stream: TextIO | None = None,
    out_stream: TextIO | None = None,
) -> None:
    """Run MCP server reading JSON-RPC messages line-by-line from stdin."""
    reader = in_stream or sys.stdin
    writer = out_stream or sys.stdout

    server = McpServer(project_folder, allow_edits=allow_edits)
    try:
        for raw_line in reader:
            line_str = raw_line.strip()
            if not line_str:
                continue
            try:
                request = json.loads(line_str)
            except json.JSONDecodeError:
                writer.write(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {"code": -32700, "message": "Parse error"},
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                writer.flush()
                continue

            response = server.handle_request(request)
            if response is not None:
                writer.write(json.dumps(response, separators=(",", ":")) + "\n")
                writer.flush()
    finally:
        server.close()
