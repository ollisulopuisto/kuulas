# Loudness, cut-candidate, transcript and recording follow-through Implementation Plan

**Goal:** Make loudness levelling reviewable, finish the remaining cut-candidate overview cue, and lock down the safe transcript and recording-health behavior already present in the app.

**Architecture:** Keep audio measurements and edits in the existing `block_level` and history paths. Add a pure overview geometry helper and draw candidate ticks in the existing canvas. Preserve the established material-revision model for transcripts and the existing recording health summary; add focused regression coverage and make the user-visible behavior explicit in help and verification docs.

**Tech Stack:** Python 3.13, pytest, plain JavaScript modules, Node test runner, Canvas 2D, English/Finnish locale catalogs.

---

## Current state checked before implementation

- `block_level.measure` already returns per-block measured level, deviation and proposed gain; `block-level-panel.js` lists only changed blocks, but the compact panel does not make the total impact or expected result obvious.
- Candidate marking, review, apply and cut-preview playback already exist. The timeline shows candidate bands; `overview.js` does not show candidate positions, although the WP18 plan calls for overview ticks.
- Transcript material revisions are already kept separately from timeline edit state. Existing tests cover `set_transcript` undo and history revision undo/redo. Extend the regression around replacing an expensive transcript, so Undo/Redo demonstrably switches saved revisions without transcription work.
- The current release already reports input overflows and inserted silence after takes, follows the live recording end in the overview, bounds live waveform work to the visible range, and skips timeline repaint while the recording dialog obscures it. Do not duplicate these paths; add/adjust regression coverage and leave real-device listening as an owner verification item.

## Task 1: Reviewable block-level loudness result

**Files:** `ui/block-level-model.js`, `ui/block-level-panel.js`, `ui/style.css`, `ui/tests/block-level-model.test.js`, `src/kuulas/locales/en.json`, `src/kuulas/locales/fi.json`, matching changelog/plan/roadmap rows.

1. Add failing pure-model tests for an impact summary (changed blocks, affected speakers/tracks, unchanged blocks) and a result level computed from measured level plus proposed gain.
2. Run the focused Node test and confirm it fails.
3. Implement the model and render a single-column, readable review list. Each changed row shows time span, measured LUFS, deviation from its speaker reference, gain to apply, and expected resulting level. Keep each row's checkbox and keep loud emphasis spots clearly separate as unchanged.
4. Show the aggregate impact before Apply; make the singular case explicit (for example, “1 block across 1 track will change”) so a one-block result is not mistaken for a session-wide operation.
5. Run focused Node tests and Biome on touched UI files. Update English/Finnish text and document the scope and limits in the help/verification material.
6. Commit this package independently.

## Task 2: Finish WP18 overview cues

**Files:** `ui/overview.js`, a pure helper in `ui/overview-segments.js` (or a narrowly scoped companion model), its Node tests, and WP18 documentation.

1. Add failing tests mapping open candidate spans to overview x positions, including candidates partly outside the timeline, tiny spans and multiple audio spans.
2. Run focused Node tests and confirm failure.
3. Draw subtle but legible candidate ticks in the overview, distinct from track audio, the visible-window box and playhead; do not change hit-testing or timeline navigation.
4. Test the geometry and run Biome for touched UI files. Update WP18 status to say the overview cue is complete and retain real-recording sound/tuning as pending owner verification.
5. Commit this package independently.

## Task 3: Transcript revision safety

**Files:** `tests/test_session.py`, `tests/test_history.py`, relevant transcript help in `ui/help/en/transcript.md` and `ui/help/fi/transcript.md`, plus docs status.

1. Add a failing session-level regression: save one transcript, replace it with a second result, undo to the first saved revision, redo to the second, and assert no worker/job was started by either history action.
2. Run the focused pytest case and confirm failure only if behavior is missing; if current behavior passes, retain the regression as proof of existing behavior.
3. Clarify in both help files that Undo/Redo switches stored transcript revisions and never reruns transcription; ordinary timeline edits do not remove transcript material.
4. Run focused tests, ruff on touched Python files, and locale/help validation. Commit independently.

## Task 4: Recording health/performance regression coverage

**Files:** `ui/record-model.js`, `ui/record-view.js` only if coverage exposes a gap, `ui/tests/record-model.test.js`, recording plan/verification docs, and release notes if behavior changes.

1. Inspect the existing health summary and live-draw performance tests from the current release; do not assume a missing feature from the screenshot alone.
2. Add focused tests for a healthy take, overflow-only take, dropout-only take and both conditions, plus the view behavior that keeps a health summary visible after stop.
3. If tests expose a UI defect, reproduce and trace it before changing code. Keep redraw work bounded to the visible recording viewport and avoid painting timeline layers covered by the dialog.
4. Run focused Node tests and Biome. Document that real input-device verification remains pending because automated tests use synthetic/fake capture.
5. Commit independently.

## Completion

Run the repository-required full Python suite and ruff; run Node UI tests and Biome because UI files are touched. Update CHANGELOG, `docs/PLAN.md` statuses, `ROADMAP.md`, README if needed, and `docs/M2-VERIFY.md` to match actual owner results. Bump CalVer in each implementation commit as required by the repo rules. Do not push or publish from this task.
