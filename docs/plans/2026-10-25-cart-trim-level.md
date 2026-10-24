# Cart trim and level Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Log only the cart audio heard during a take, at a matched level.

**Architecture:** Pure frame trim and peak guarded gain functions feed dedicated session commands. RecordSession owns logged clip identities and the take clock. The preview endpoint prepares matched audio; the UI reports preview ends and keeps a manual trim preference.

**Tech Stack:** Python, FastAPI, plain JavaScript, pytest, node:test.

### Task 1: Pure arithmetic
- Add tests/test_cart_level.py for full/early/late/before-start stops and gain boost/cut/ceiling/trim/reference fallback.
- Run `uv run --offline pytest -q tests/test_cart_level.py` and observe missing functions.
- Implement src/kuulas/cart_level.py; rerun tests.

### Task 2: Recording commands
- Extend tests/test_record_session.py with scoped stop, replacement, paused edit refusal and stored gain cases; observe failures.
- Add Session cart end command and gain on paste in a single history commit; RecordSession tracks active IDs and samples a three-second voice estimate.
- Wire server preview and end endpoint; run recording and session tests.

### Task 3: UI lifecycle and preference
- Add node tests for preview tracking and trim preference control; observe failure.
- Wire preview start/replacement/stop events and take end. Add remembered trim in Clipboard with English/Finnish label and help.
- Run all node tests, offline pytest and ruff. Biome is deferred to coordinator as C7 directs.

Stops before start retain one frame. No recorded file is changed. No schema or version change.
