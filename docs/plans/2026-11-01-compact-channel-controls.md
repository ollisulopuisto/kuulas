# Compact Channel Controls Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep channel headers at 160 CSS pixels and move gain, pan, and routing controls into an accessible flyout that never changes timeline geometry.

**Architecture:** Headers retain the track color, truncated name, mute/solo, and a controls trigger. A single fixed-position flyout is portaled to the document body and reuses the track's existing slider and routing elements. Hover opens it after a short delay; the trigger opens it on click or keyboard; focus and pin keep it open; Escape and outside interaction close it.

**Tech Stack:** Browser UI modules, CSS, English/Finnish locale JSON, Node test runner, Biome.

---

### Task 1: Model flyout opening and pinning

**Files:** Create `ui/track-controls-model.js` and `ui/tests/track-controls-model.test.js`.

Write failing tests for delayed-hover intent, explicit open/toggle, pin/unpin, switching tracks, and escape/outside close. Keep the state model pure and verify the new test file independently.

### Task 2: Reduce the stable header and move controls into a flyout

**Files:** Modify `ui/tracks.js`, `ui/style.css`, `ui/tokens.css`, `ui/tests/track-control-layout.test.js`; add English and Finnish strings in `src/kuulas/locales/en.json` and `fi.json`.

Write failing structure and layout regressions first. Keep the color stripe, truncated name, M/S buttons, and controls trigger in a 160px column. Portal the existing gain, pan, kind/role, and bus controls to one fixed overlay. Wire hover delay, click/keyboard toggle, focus retention, pin, Escape, outside close, and position updates on track-list scrolling/resizing. Assert opening and closing do not mutate layout width variables.

### Task 3: Verify and commit

Run the new tests alone, `node --test ui/tests/`, Biome, Ruff, and the required Python suite where the environment allows. Review `git diff --check` and commit locally without pushing.
