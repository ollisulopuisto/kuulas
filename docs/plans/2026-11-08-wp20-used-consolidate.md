# WP20 Used-Only Consolidation Implementation Plan

> **For Codex:** Follow this plan with red-green TDD; keep audio reading bounded and publish files atomically.

**Goal:** Let callers preview and run an opt-in consolidation that keeps only the ranges used by timeline clips, with two-second handles, while preserving clip positions and the ability to relink the complete source.

**Architecture:** Reuse WP20's existing used-range calculation from `send_copy.py`. `MediaStore` writes a full-length sparse FLAC with silence outside those ranges and records the original size/ranges so relinking can restore the verified original. `Session` exposes a conservative proportional byte estimate and opts in through `consolidate({used_only: true})`; the existing default remains full consolidation.

**Tech Stack:** Python, NumPy, SoundFile, SQLite, pytest, existing Session command API.

---

### Task 1: Used-only media storage

**Files:**
- Modify: `src/kuulas/media.py`
- Test: `tests/test_used_consolidate.py`

1. Write failing tests for sparse consolidation preserving frame count and used samples, silencing unused spans, leaving unused media linked, and recording partial-copy metadata.
2. Run `uv run pytest -q tests/test_used_consolidate.py`; confirm the used-only API is missing.
3. Add a bounded, atomic partial-FLAC writer to `MediaStore`; update metadata only after the file is durable, and preserve normal full consolidation when no ranges are supplied.
4. Verify a full-source relink restores original samples and partial-write failure leaves the media linked with no partial output.

### Task 2: Session plan and command

**Files:**
- Modify: `src/kuulas/session.py`, `src/kuulas/server.py`
- Test: `tests/test_used_consolidate.py`, `tests/test_server.py`

1. Test a plan that reports used frame ranges, the two-second handles, and a proportional size estimate; test the session command leaves project state/history unchanged.
2. Add `Session.consolidate_plan()` and `GET /api/media/consolidate-plan`.
3. Validate `used_only` as a boolean and pass current project ranges into storage; keep the existing no-argument behavior unchanged.
4. Run the new test file alone, then the full Python suite and Ruff.

### Task 3: Review and commit

1. Run `git diff --check` and review the stored metadata, relink flow and API response.
2. Commit locally on `codex/wp20-used-consolidate`; leave UI controls and release documentation to follow-up integration.
