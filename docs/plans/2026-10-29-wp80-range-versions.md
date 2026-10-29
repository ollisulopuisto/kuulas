# Versions of this part Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Recover earlier contents of a track range without rolling back later edits.

**Architecture:** Derive distinct range snapshots from all stored edit states, including abandoned branches. Restore only the chosen track range through the ordinary overwrite operation and commit a new history step. Existing project format and media remain unchanged.

**Tech Stack:** Python frozen dataclasses, SQLite history, browser JavaScript.

### Task 1: Range snapshots

Create `src/kuulas/part_versions.py` and `tests/test_part_versions.py`. First test three recordings, repeated contents, split clips, gaps and range clipping. Run the new test file and observe missing-module failure. Implement immutable range snapshots and content signatures, newest-first deduplication with occurrence metadata.

### Task 2: Restore

Add a pure operation in `src/kuulas/ops.py`, using `clear_range` and newly identified clips. Test source bounds, preservation of other tracks, gain, envelopes, gates and later edits, and undo via Session. Run regressions before implementation.

### Task 3: Integration

Expose history states read-only, with Session inspection and restore APIs; add a user-accessible command and range-version chooser. Keep expensive history traversal off the event loop. Translate labels in both locale files.

### Task 4: Validation

Run new files alone, full `uv run pytest -q`, `uv run ruff check .`, `node --test ui/tests/`, and `npx --yes @biomejs/biome@2.2.4 check ui/`. Commit locally and report remaining manual listening checks.
