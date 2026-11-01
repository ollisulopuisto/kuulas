# Roadmap Reorder Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make ROADMAP.md readable from current release to the next milestone work while preserving all requirements, decisions, and historical notes.

**Architecture:** Treat `docs/PLAN.md` as the work-package source and `docs/BUGS.md` as the owner-verification source. Put current status and ordered milestones first, then requirements and open decisions, with release history and older snapshots after the active roadmap.

**Tech Stack:** Markdown; `python scripts/check_docs.py` for roadmap/package consistency.

---

### Task 1: Establish the current roadmap entry point

**Files:**
- Modify: `ROADMAP.md`

Add the current release, remaining owner checks, and a short guide to the milestone order. Use v26.11.1.1 and the committed source as the baseline; do not claim that owner-only UI or hardware checks are complete.

### Task 2: Put ordered milestone work before the requirement catalog

**Files:**
- Modify: `ROADMAP.md`
- Reference: `docs/PLAN.md` Triage

Move the existing milestone status block near the top, clarify each milestone's open/partial package sequence and dependencies from the plan, and keep owner acceptance work separate from implementation tasks.

### Task 3: Preserve supporting material in a readable order

**Files:**
- Modify: `ROADMAP.md`

Keep the requirement catalog and active open questions after the milestone order. Group dated release notes, superseded build snapshots, and older owner ideas under clearly named history/idea sections without deleting or silently changing their decisions.

### Task 4: Validate the document

Run `python scripts/check_docs.py`, inspect the full diff, and confirm all WP identifiers and owner decisions remain present. Commit locally on `docs/roadmap-order`; do not push.
