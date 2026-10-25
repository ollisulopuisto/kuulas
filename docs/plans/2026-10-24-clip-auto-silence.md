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


### Follow-up: open portions are implicit too (owner, 2026-10-24)

The 4:08.967 screenshot is an audible opening between closed stretches. The old
hit target and mute planner recognize only closed ranges and therefore mute the
whole parent. Both open and closed portions must use the same boundaries.

1. Add failing Python tests in `tests/test_clip_silence.py` for muting an open
   portion, legacy gates, dragging either type of portion, and exemption after
   moving and running Auto-Silence again. Add Node tests in
   `ui/tests/clip-silence-model.test.js`, `ui/tests/edit-plans.test.js`, and
   `ui/tests/edge-drag.test.js` for matching hit targets, M, drag limits, and
   selecting the resulting explicit clip.
2. Add pure portion arithmetic; use it in `ops.py` and `ui/clip-silence.js`.
   Update hit testing, mute planning, and edge drag to target the same portion.
   Mark materialized clips `ungated=True`, clear their implicit ranges, and
   preserve that choice on subsequent analysis. No recordings are modified.
3. Owner clarified: do not overload double-click with muting. Preserve envelope
   editing, missing-media location, and placeholder editing; remove the old
   Auto-Silence double-click action. No new preference or body action.
4. Keep BUGS #120 fixed-but-awaiting-owner-check, document the behavior, run
   focused tests red/green and required full checks, then build/tag/publish .3.


**Follow-up validation:** the new open-portion tests first failed because M planned
`set_clips`, the backend rejected an open portion, and materialization did not set
`ungated`. The group regression separately failed because the explicit result
still expanded to its parent's siblings. The old whole-parent expectation outside
a closed stretch was changed to the owner's audible-portion toggle contract;
legacy gate plans now name the clicked clip explicitly.

Final checks: 5,046 pytest, 3,394 Node tests; Ruff and Biome 2.2.4 pass. A headless
Chrome check against an isolated synthetic two-track project confirms the actual
4:08.967 click + M, second M, dotted-edge drag, exemption on re-analysis, body
double-click making no edit, and envelope-point add/remove by double-click. The
owner's real project was not opened or changed; BUGS #120 still awaits confirmation.
