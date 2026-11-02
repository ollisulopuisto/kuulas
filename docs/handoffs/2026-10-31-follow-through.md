# 2026-10-31 follow-through checkpoint

Branch/worktree: `feat/editor-followthrough` at `/private/tmp/kuulas-editor-followthrough`, based on `262980b` (`v26.10.30.6`). The original checkout at `/Users/dst/Documents/koodi/kuulas` remains on clean `main`. Nothing has been pushed or released.

## Completed

- Block-level levelling review shows measured level, deviation, proposed gain and a live impact summary; Apply disables when nothing is selected.
- CI uses Node 24 and `dorny/paths-filter@v4`; independent Python, Ruff and UI jobs run in parallel, with change-path filters to skip unaffected groups. Manual dispatch still runs every group.
- Short-project shuttle regression accounts for one minimum-length grain and final 256-frame block rounding.
- Overview draws subtle candidate ticks for every visible open candidate span. Geometry tests cover spans outside the edit, tiny spans and multiple spans.
- Transcript revision regression replaces a transcript, then verifies Undo/Redo switches saved revisions without launching a worker or background job. English and Finnish help explains that history does not rerun transcription and timeline edits keep transcript material.
- Recording health tests cover a healthy take, overflow-only, dropout-only and both; notices remain sticky when a take has capture problems. Existing live-take tests cover bounded viewport columns and live head placement; the app skips timeline repaint while the recording dialog is visible.
- Regenerated `docs/KEYS.md` and synced the design prototype from canonical sources. Updated plan and verification notes.

## Verification

- Full Python suite, with process permissions needed by the worker-priority test: `5396 passed, 7 skipped`.
- Ruff: clean.
- Full Node suite: `3648 passed`.
- Focused session and keys-doc tests: `62 passed`; transcript revision regression passes.
- Focused overview, recording model and help tests: `88 passed`.
- Biome could not run because npm registry DNS lookup failed (`ENOTFOUND registry.npmjs.org`).

## Owner verification

The real input-device recording check and listening/tuning of candidate ticks on real material remain owner tasks. No device behavior was simulated or claimed as verified here.
