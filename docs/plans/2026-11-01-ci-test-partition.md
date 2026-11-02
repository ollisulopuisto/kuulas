# CI Test Partitioning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep Python test coverage on product-code changes while running only changed test modules for test-only pull requests. Split full suites across deterministic shards, with scheduled and manual full-suite runs.

**Architecture:** Split CI change detection into full-Python and test-module-only paths. The test-only path passes changed module paths as JSON to a small Python runner that validates paths and invokes pytest without shell interpolation. Full-suite runs divide the same stable pytest collection into two disjoint shards on each OS. Source, shared fixtures, workflow, configuration, deleted test modules, and scheduled/manual runs keep the complete Python suite enabled.

**Tech Stack:** GitHub Actions, `dorny/paths-filter@v4`, Python, pytest, Node tests, Ruff, Biome.

---

### Task 1: Select changed test modules safely

**Files:**
- Create: `scripts/run_changed_pytests.py`
- Create: `tests/test_ci_test_selection.py`

**Step 1: Write failing tests** for selecting existing root-level `tests/test_*.py` files, sorting/deduplicating them, and rejecting paths outside the test-module pattern or files that no longer exist.

**Step 2: Run the new test file** with `PYTHONPATH=src pytest -q tests/test_ci_test_selection.py` and confirm it fails because the selection helper does not exist.

**Step 3: Implement** a pure path-validation/selection helper and a runner that reads a JSON array from an environment variable, passes validated paths as an argument list to pytest, and reports when a change contains only deleted test modules.

**Step 4: Run the test file and Ruff**; all new tests must pass and the runner must be lint-clean.

### Task 2: Route PRs to targeted or full Python coverage

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Change path filters** so changes to source code, shared test support, configuration, dependencies, docs-derived assets, scripts, or workflows request the full Python suite. Root-level added/modified `tests/test_*.py` files get a separate changed-module list; deleting a test module requests the full suite.

**Step 2: Add a weekly scheduled full run** and keep `workflow_dispatch` as an explicit full run. UI and Python lint filters remain independent.

**Step 3: Update the Python test job** to run all tests for full-suite changes across two deterministic shards and both OSes, or invoke the safe changed-module runner for test-only changes. Upload a distinct JUnit report for every OS/shard.

**Step 4: Validate workflow routing** for UI-only, Python-source, one-test-module, shared-fixture, test-module deletion, manual, and scheduled changes. Confirm each production-code change still runs every Python test and that no test path is interpolated into shell code.

### Task 3: Verify and commit

**Files:**
- Verify: `tests/test_ci_test_selection.py`, `.github/workflows/ci.yml`

**Step 1:** Run the new test file on its own, Ruff, all UI tests, and Biome.

**Step 2:** Run the full pytest suite if the environment permits; CI's full-suite paths remain enabled for source and shared-fixture changes.

**Step 3:** Review the final diff, run `git diff --check`, and commit locally. Do not push.
