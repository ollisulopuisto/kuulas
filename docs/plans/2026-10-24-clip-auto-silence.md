# Clip Auto-Silence Editing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Auto-Silence follow the audio clip it measured, expose its muted portions as editable implicit clips, and detach transcript follow when the user scrolls it.

**Architecture:** Preserve Auto-Silence analysis as derived ranges, but anchor those ranges to clip source time instead of track timeline time. Render each closed range as an implicit muted segment; the first direct edit (mute or edge drag) materializes just that segment into ordinary clips in one history step. Keep clip border styling distinct from waveform colors, and add transcript scroll as a follow-detach event while playback is active.

**Tech Stack:** Python frozen project model/ops/mixer/session, plain JavaScript UI modules and Node's built-in tests, existing pytest/Ruff/Biome checks.

---

### Task 1: Lock the interaction contracts in tests

**Files:** `ui/tests/follow-model.test.js`, `ui/tests/transcript-*.test.js`, `ui/tests/clip-drag.test.js`, UI tests for mute planning, and new Python model/ops/mixer tests as needed.

**Steps:** Add tests that scrolling the transcript while playing detaches Follow; stopped scrolling does not change it; implicit silence is tied to clip media/source position and moves with its clip; M toggles only the implicit portion; dragging an implicit edge converts that portion to explicit clips; and border color is not the waveform token. Run each focused test and record the expected failures.

### Task 2: Attach measured silence and settings to a clip

**Files:** `src/kuulas/model.py`, `src/kuulas/analysis.py`, `src/kuulas/ops.py`, relevant mixer/session/API files and Python tests.

**Steps:** Add an optional per-clip Auto-Silence configuration and source-frame closed ranges with byte-preserving defaults. Update analysis and audibility so clip-local ranges move with their clip and are unaffected by clips moved into another clip's formerly silent track-time span. Keep unrelated legacy track gates readable. Test serialization, move/trim behavior, and audio masking.

### Task 3: Materialize implicit portions on direct edits

**Files:** `src/kuulas/ops.py`, `ui/edit-commands.js`, `ui/clip-drag.js`, `ui/timeline.js`, corresponding Python and Node tests.

**Steps:** Give implicit portions stable hit targets and boundaries. On M or a boundary drag, split only the affected parent clip at the region edges, preserve source offsets and clip fields, then apply the mute or trim as one normal edit. Verify undo restores the implicit representation and adjacent clips remain unchanged.

### Task 4: Transcript follow and signal styling

**Files:** transcript follow wiring, `ui/silence-visuals.js`, theme CSS/tokens and UI tests.

**Steps:** Route transcript user scrolling through the same Follow state machine as timeline view operations. Give clip edges their own theme token, separate from track waveform colors, in both themes. Verify keyboard scroll, wheel, and touch/drag scrolling behavior.

### Task 5: Validate and commit

Run focused tests individually, then the required full Python/UI tests and linters. Update the relevant plan/changelog/roadmap status only if the corresponding work package is within this branch's scope, and commit locally.
