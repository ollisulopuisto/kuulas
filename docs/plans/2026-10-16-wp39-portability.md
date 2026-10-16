# WP39 Portable Projects Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let linked media follow a project across machines with different filesystem roots, always verified by content hash.

**Architecture:** Store package and series relative paths with linked-media metadata; keep media folders and learned root rewrites in a per-user settings file. Resolve paths in the specified order on a background worker, and use explicit relink choices to learn a rewrite for other missing files.

**Tech Stack:** Python pathlib, SQLite migration, SHA-256, JSON settings, pytest.

---

### Task 1: Relocation tests

Test project-root copies, media-folder lookup by hash and size, learned rewrites, and rejection of same-named wrong content. Run the focused tests first and record the expected failures.

### Task 2: Persist relative linked paths

Add package-relative and optional series-relative path fields to media storage, including an additive SQLite migration and FORMAT documentation.

### Task 3: Per-user media paths and resolver

Read/write media folders and learned rewrites in per-user settings. Resolve relative paths, explicit/configured media roots, then remembered paths; verify every candidate hash and update the in-memory offline state safely.

### Task 4: Relink one, resolve the rest

Add a single-media relink operation that verifies the chosen file, learns a common path-prefix rewrite, applies it to other missing media, and persists the rewrite per user.

### Task 5: Validate and hand off

Run focused, full Python tests and Ruff. Update project documentation and release status when integrating this worktree; commit locally only.

**Progress:**

- Added relocation tests first and confirmed they failed on the absent resolver
  and relink APIs.
- Added schema v3 linked path fields, asynchronous hash-verified resolution,
  per-user media folders and root rewrites, and explicit single-file relinking.
- Documented resolver order and portability settings in `docs/FORMAT.md`.
- Focused test suite: 4 passed; full suite: 417 passed with one existing
  Starlette deprecation warning. Ruff: clean.
- Manifest/release version and roadmap status remain for branch integration,
  per the worktree handoff rules.
