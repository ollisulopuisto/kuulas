# PR #5 Cross Platform CI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Windows and Linux jobs proposed by PR #5 pass on the current main branch, while recording any platform feature limits clearly.

**Architecture:** Keep the CI matrix explicit. Put platform runtime requirements in the project environment, make platform-specific tests say which platform behavior they exercise, and keep Unix-only recorder, analysis, and detached-transcription worker coverage plus macOS-only automixer integration on supported systems until Windows implementations exist.

**Tech Stack:** GitHub Actions, Python 3.13, uv, pytest, Ruff.

---

### Task 1: Reproduce and classify PR #5 failures

Inspect the failed run logs and current main branch. Keep Windows timezone support in the uv environment, identify recorder tests that depend on Unix-only `fcntl`, confirm Linux's ffmpeg codec-dependent test assumptions, and isolate the Cocoa-only test from the host OS.

### Task 2: Add regression coverage before fixes

Add focused tests or correct platform-bound test setup first. Run each changed test file and confirm the old behavior fails for the reported reason.

### Task 3: Fix platform dependencies and workflow matrix

Add Windows tzdata as a platform-marked dependency, enable the three-platform CI matrix, and exclude recorder, analysis-worker, and detached-transcription worker tests that rely on Unix process behavior and automixer tests that rely on macOS process and path behavior from Windows. Keep Linux and macOS running the full test suite.

### Task 4: Make tests deterministic across hosts

Use an invalid format identifier for unsupported-format tests, set Darwin explicitly in the fake Cocoa hook test, and remove scheduler-dependent assertions from recorder tests only if they can be replaced with an invariant-based assertion.

### Task 5: Verify and commit

Run focused tests, full pytest, Ruff, UI tests, and Biome. Review the diff, update README's CI/platform note, and commit locally without pushing.

### Task 6: Keep Kuulas compatible with the current podcast transcription tool

Prefer the sibling `../podcast/colab-transcribe` project when running from a source checkout, while keeping the public GitHub fallback for packaged installs. Accept Orukeet's unaligned timing label and verify that filler and repetition words survive the Colab result reader.
