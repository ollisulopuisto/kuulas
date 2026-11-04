"""Tests for kuulas mcp server (WP53)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import stub_podcast  # noqa: F401

from kuulas.mcp_server import McpServer, serve_stdio


def test_mcp_initialize(tmp_path: Path):
    server = McpServer(tmp_path)
    res = server.handle_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    })
    assert res is not None
    assert res["id"] == 1
    assert res["result"]["serverInfo"]["name"] == "kuulas"
    assert "tools" in res["result"]["capabilities"]


def test_mcp_tools_list(tmp_path: Path):
    server = McpServer(tmp_path)
    res = server.handle_request({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
    })
    assert res is not None
    tool_names = [t["name"] for t in res["result"]["tools"]]
    assert "get_project_state" in tool_names
    assert "get_heard_words" in tool_names
    assert "search_transcript" in tool_names
    assert "list_commands" in tool_names
    assert "execute_edit" in tool_names
    assert "execute_command" in tool_names
    assert "undo" in tool_names
    assert "redo" in tool_names


def test_mcp_resources_and_prompts(tmp_path: Path):
    server = McpServer(tmp_path)
    res_list = server.handle_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "resources/list",
    })
    uris = [r["uri"] for r in res_list["result"]["resources"]]
    assert "kuulas://project/state" in uris
    assert "kuulas://project/words" in uris
    assert "kuulas://project/commands" in uris

    prompt_list = server.handle_request({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "prompts/list",
    })
    prompts = [p["name"] for p in prompt_list["result"]["prompts"]]
    assert "review_transcript" in prompts
    assert "summarize_project" in prompts


def test_mcp_read_only_mode_refuses_mutations(tmp_path: Path):
    server = McpServer(tmp_path, allow_edits=False)
    # execute_edit
    res = server.handle_request({
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "execute_edit",
            "arguments": {"op": "split_clip", "args": {"clip_id": "c1", "at": 100}},
        },
    })
    assert res["result"]["isError"] is True
    assert "disabled" in res["result"]["content"][0]["text"]

    # execute_command
    res = server.handle_request({
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "execute_command",
            "arguments": {"name": "cut_words", "args": {"indices": [0]}},
        },
    })
    assert res["result"]["isError"] is True
    assert "disabled" in res["result"]["content"][0]["text"]

    # undo
    res = server.handle_request({
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "undo"},
    })
    assert res["result"]["isError"] is True
    assert "disabled" in res["result"]["content"][0]["text"]


def test_mcp_queries_and_live_routing(tmp_path: Path):
    server = McpServer(tmp_path, allow_edits=True)

    fake_state = {"project": {"tracks": [{"name": "Voice"}]}, "head": "head1"}
    fake_words = [{"w": "hello", "s": 0, "e": 1000}]

    with (
        patch.object(server, "get_state", return_value=fake_state),
        patch.object(server, "get_words", return_value=fake_words),
    ):
        # 1. State tool
        res1 = server.handle_request({
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "get_project_state"},
        })
        parsed1 = json.loads(res1["result"]["content"][0]["text"])
        assert parsed1["head"] == "head1"

        # 2. Words tool
        res2 = server.handle_request({
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "get_heard_words"},
        })
        parsed2 = json.loads(res2["result"]["content"][0]["text"])
        assert parsed2[0]["w"] == "hello"

        # 3. Search transcript
        res3 = server.handle_request({
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "search_transcript", "arguments": {"query": "ell"}},
        })
        parsed3 = json.loads(res3["result"]["content"][0]["text"])
        assert len(parsed3) == 1
        assert parsed3[0]["w"] == "hello"

        # 4. Resource read
        res4 = server.handle_request({
            "jsonrpc": "2.0",
            "id": 13,
            "method": "resources/read",
            "params": {"uri": "kuulas://project/words"},
        })
        parsed4 = json.loads(res4["result"]["contents"][0]["text"])
        assert parsed4[0]["w"] == "hello"

        # 5. Prompt get
        res5 = server.handle_request({
            "jsonrpc": "2.0",
            "id": 14,
            "method": "prompts/get",
            "params": {"name": "summarize_project"},
        })
        assert "Voice" in res5["result"]["messages"][0]["content"]["text"]


def test_serve_stdio(tmp_path: Path):
    in_buf = io.StringIO(
        json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        })
        + "\n"
    )
    out_buf = io.StringIO()

    serve_stdio(tmp_path, in_stream=in_buf, out_stream=out_buf)
    out_lines = out_buf.getvalue().strip().split("\n")
    assert len(out_lines) == 1
    resp = json.loads(out_lines[0])
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "kuulas"
