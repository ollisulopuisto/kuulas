# Agent API and MCP Implementation Plan

**Goal:** Let an MCP-compatible local agent inspect a Kuulas project, transcribe its media, review filler/repetition candidates, and make approved edits through the same commands as the UI.

**Architecture:** Add an optional MCP stdio server backed by `Session`, so it works headlessly and reuses the session command table and command catalog. The server is read-only by default; transcription and edits require an explicit `--allow-edits` launch option, and destructive candidate application additionally requires an explicit confirmation argument. Keep the existing HTTP API unchanged.

**Tech Stack:** Python 3.13, official MCP Python SDK v1 API, pytest, Ruff.

---

### Task 1: MCP server with safe read tools and catalog-driven actions

**Files:**
- Create: `src/kuulas/mcp_server.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/test_mcp_server.py`

**Step 1: Write failing tests**
- Verify project overview and transcript words are readable.
- Verify command listing is derived from the existing catalog.
- Verify transcription and generic mutating calls fail when edit access is disabled.
- Verify candidate apply requires both enabled edit access and explicit confirmation.
- Verify allowed transcription submits jobs and returns job IDs.

**Step 2: Run the MCP server tests and confirm the intended failures.**

**Step 3: Implement a small MCP server factory that accepts an existing `Session` and an `allow_edits` flag.**
- Read tools: project summary, media inventory, transcript words, command catalog, jobs, candidate listing, and candidate preview.
- Mutating tools: start transcription, invoke catalogued edit/session commands; reject calls whose catalog entry is mutating unless edits were enabled at launch.
- Candidate apply also requires `confirm=true` and returns the edit result.
- No tools expose file deletion or arbitrary shell execution.
- Add a `kuulas-mcp` entry point, and keep MCP as an optional `agent` extra.

**Step 4: Run the MCP server test file and confirm it passes.**

**Step 5: Run Ruff on changed Python files and verify MCP stdio starts with the official SDK.**

**Step 6: Commit the focused implementation.**

### Task 2: Agent workflow documentation

**Files:**
- Modify: `docs/SCRIPTING.md`
- Modify: `tests/test_mcp_server.py` (documentation/config examples as useful)

**Step 1: Add an agent quick start for configuring `kuulas-mcp` in an MCP host.**
- Include read-only and editable configurations.
- Show the requested workflow: enumerate media, transcribe, poll jobs, detect candidates, inspect previews, apply confirmed edits.
- Explain local processing versus Colab, existing Colab sign-in requirement, and that private audio is sent only according to the selected backend.
- Explain that a locked open project is readable but cannot be edited through a second session.

**Step 2: Add a test that the documented tool names match the registered MCP tool names.**

**Step 3: Run focused tests and Ruff, then commit documentation and coverage.**
