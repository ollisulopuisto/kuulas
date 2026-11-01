# 2026-11-01: inline rename for bus headers (and the existing track-header rename)

Branch: `feat/bus-inline-rename`, from `main` at `03327df4` (v26.11.1.2 prep).

Owner request (iMessage, 2026-11-01): rename a track by double-clicking its
name in the header, and the same for buses.

## What existed

- Track headers already renamed inline on double-click (WP4, `b5c366ed`):
  the name button swaps for a text field, Enter/blur commits, Escape cancels.
- Bus headers did not: the name was a plain span and a double-click anywhere
  on the header only folded/unfolded the bus.
- Keyboard/menu path unchanged and preserved: F2 / `rename` command focuses
  the Inspector name field for the current track or bus; Inspector renaming
  and undo/history behavior untouched.

## Change

- `ui/tracks.js`: the header rename helper now takes the row kind and commits
  `set_bus`/`patchBus` for buses (the same op the Inspector uses) while tracks
  keep `set_track`/`patchTrack`. The commit decision (non-empty, changed,
  trimmed) is the exported pure `renamedName`, shared by both.
- The bus name span got the rename tooltip (`ui.bus.rename`, en + fi) and a
  double-click handler that stops propagation, so renaming never folds the
  bus; folding still works from the rest of the header row.
- Rename commits go through `editor.change`, so they are ordinary undo steps
  exactly like Inspector renames.

## Verification

- `node --test ui/tests/*.test.js`: 3659 passed (5 new in
  `ui/tests/track-bus-rename.test.js`, written failing first).
- `npx @biomejs/biome@2.2.4 check ui/tracks.js ui/tests/track-bus-rename.test.js`: clean.
- `uv run pytest -q tests/test_check_locale.py`: 10 passed (locale parity).
- `uv run ruff check .`: clean. No Python code changed.
- Not verified: actual rendered behavior in the packaged app (no display
  here); the owner sees it after merge + DMG.

## Follow-ups

- DMG: `dmg.yml` workflow_dispatch on the merged main head gives the owner a
  tester DMG (artifact, 30 days); a versioned release DMG stays the
  integrator's tag flow.
