# C8 Automation Snap Implementation Plan

**Goal:** Enable held Cmd/Ctrl automation snapping for edge trims and clipboard drops.

**Architecture:** Reuse automationTargets through a small drag snap session with primary targets tried first. Keep existing trim modes and selection rules; expose transient marks for the shared overlay drawing.

**Tech Stack:** Plain JavaScript, Node test runner, canvas UI.

### Task 1: Pure snapping and lifecycle

- Create `ui/drag-snap.js` and `ui/tests/drag-snap.test.js`.
- Write tests for edge and clipboard target exclusions, modifier on/off, Alt, primary priority, and marks cleared on end/cancel.
- Run tests and observe missing-module failure, then implement the helper with `automationTargets`, `moveTargets`, and `snapMove`.

### Task 2: Clipboard drop

- Add failing cases in `ui/tests/clipboard-drag.test.js` for automation drop snapping, priority and preview mark cleanup.
- Wire `ui/clipboard-drag.js` to the helper; pass the live modifier from `ui/timeline.js` and draw its preview marks.

### Task 3: Edge trim

- Wire the helper into `startEdge`, `clampEdge`, and `endEdge` in `ui/timeline.js`.
- Read the existing live modifier without changing alone/overwrite/ripple or selection handling. Clamp snapped positions through existing edge limits.
- Extract existing automation tick drawing for reuse by both new drags.

### Task 4: Verify and report

- Run `node --test ui/tests/` and `uv run --offline ruff check .`; attempt offline pytest before committing.
- Skip Biome per C8 assignment. Review diff, commit locally with Codex attribution, append coordinator report.
- Report browser wiring and real-episode snap feel as unverified.
