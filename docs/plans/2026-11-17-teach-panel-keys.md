# Teach the two-step panel keys (2026-11-17)

The modal number keys (`fix/cart-modal-only`, same day) made 1-9 and 1-7 act only inside
Markers and Clipboard; the timeline keeps 1/2 for In and Out as the only global number
keys (owner, 2026-11-17). A removed habit needs teaching in its place. The owner picked
all four options:

1. **Show the number** - already shipped: tabs carry their `Cmd+n`, marker rows carry
   permanent number badges, Clipboard rows show the cart chip.
2. **Use the status bar** - two lessons, both only until the pattern has been done once:
   - When Markers or Clipboard opens, the status bar says what a bare number now does
     ("Now a bare 1-9 jumps to a marker." / "...1-7 plays a cart slot.").
   - When a bare digit pressed away from its panel does nothing (not typing, not
     modified, not held, not behind a dialog, not already in a number panel), the status
     bar says where numbers act ("Number keys act inside their panel: ...").
   - Panels' status-bar hints now lead with the bare-number action: Markers and
     Clipboard show `1` first.
3. **Onboarding tasks** - a sixth core-loop row, "Two-step panel keys", the only row
   that needs two different halves: open a number panel (Markers or Clipboard), and run
   a bare-number action in one (jump to a marker, play a cart slot). Either half first;
   half-done progress persists in the panel state.
4. **Cheat sheet** - the existing `?` sheet opens with one teaching line naming the
   pattern and the timeline exception; it steps aside while searching.

## Files

- `ui/status-teach.js` (new) - the gating (`teachForCommand`, `teachForDeadDigit`) and
  the teacher (`createStatusTeacher`), which borrows the menu-hint spot for five
  seconds and restores what was there; a menu's own hint is never cleared by it.
- `ui/core-loop-model.js` - steps-rows: a row may need one command from each of several
  groups; `steps` persists half-done progress; `PANEL_COMMANDS` / `NUMBER_COMMANDS` are
  exported for the teacher.
- `ui/core-loop-panel.js` - steps-rows render an example with an arrow (panel key, `->`,
  bare number).
- `ui/shell-keys.js` - wires the teacher: command-ran hook and dead-key correction,
  gated on the core-loop state.
- `ui/keymap-default.js` - `STATUS_HINTS` for `markers` and `clipboard`.
- `ui/cheatsheet.js`, `ui/style.css` - the teaching line and its style.
- `src/kuulas/locales/{en,fi}.json` - the words, both languages.
- `ui/tests/teach-panel-keys.test.js` (new), `ui/tests/core-loop.test.js` - the logic,
  the hints, the cheat-sheet line, the steps-row.

## Validation

- `node --test ui/tests/*.test.js`
- `npx --yes @biomejs/biome@2.2.4 check ui/`
- `uv run pytest -q tests/test_check_locale.py tests/test_keys_doc.py tests/test_check_docs.py`
- `node docs/design/sync-tokens.mjs` (locale change regenerates the prototype)
