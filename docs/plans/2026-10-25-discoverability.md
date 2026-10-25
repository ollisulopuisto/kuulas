# Discoverability: power features findable from the GUI

Status: plan only (2026-10-25). Nothing here is built. Part of WP48 (R59, R60).

Owner, 2026-10-25: "We are targeting power users and keyboard shortcuts, but we DEFINITELY need a
way to surface these features in the GUI so people can discover them."

## Constraints (already decided)

- No floating tool palette (WP47: no floating windows; no spare space in the pywebview window).
- Menus, keymap and command registry stay the single source of truth; "menus show everything"
  (`ui/tests/menu-coverage.test.js`). Every surface below *reads* the registry, never copies it.
- Never a hand-written key name in user text: keys come from the keymap at render time
  (`{key:id}` in help bodies, `format(raw, platform)` elsewhere), so a remapped key shows remapped.
- Finnish layout: no default key needing AltGr or Shift+digit (memory rule); new surfaces add no keys
  that break it.
- Owner Q23 (2026-10-18): tips are **hover tips** (short hint + key on hover), not a timed tip
  every N minutes. Item 2 below is post-action and capped, but it is a tip; see question 1.
- Every new string: message key, en + fi in the same commit (R39).

## What exists today (do not rebuild)

- Menus with keys; menu title flash when a key chord runs (`ui/menu-flash.js`).
- Help search (field in Help menu; shows menu path, Alt+Enter opens the menu at the item) and the
  command palette, one matcher: `ui/command-search.js`; synonyms en+fi in `ui/command-synonyms.js`.
- Cheat sheet (`help.keys`, `ui/cheatsheet.js`), generated from the live keymap, Alt/Shift layers.
- Status-bar key hints, three per focused panel (`STATUS_HINTS` in `ui/keymap-default.js`,
  `ui/hints.js`, `#keyhints`).
- Contextual help panel, F1, 14 topics as data (`ui/help/<lang>/*.md`, `{key:}` tokens).
- Help > Getting started submenu (`ui/menu-model.js`: import, play, split, transcribe, export,
  palette).
- Empty-state strings for most panels (`ui.*.empty`), recent-commands group in the palette.
- `ui/tip-model.js`: hover-tip state machine, tested, **not wired to any element**.
- Working tree (uncommitted, other session): keys in header context menus, right-click menus for
  placeholder, transcript words, clipboard row, ruler markers; track drag handle.

## Defects found while reading (fix first, they are cheap)

- 27 English strings carry literal keys, e.g. `ui.markers.empty` says "Press M" but `marker.add`
  is Mod+Enter (M is `clip.mute`). Others: `ui.cart.empty`, `ui.candidates.empty` ("with D"),
  `ui.search.footer`, several `cmd.*.hint`. Replace with `{key:id}` placeholders filled at render.
- `aria-keyshortcuts` in `ui/index.html` is hand-written (`Z`, `-`, `=`); fill from the keymap.
- Transport/zoom buttons use `title` with the hint only, no key.

---

## Items

### 1. Empty-state / first-run hints per panel

What the user sees: each empty panel says the one next step and shows a real button for it with its
key (button runs the command; key text from the keymap). Timeline empty: drop zone + "Import audio"
button + "or drag files here". Transcript empty: "Transcribe" button. Candidates, markers, cart,
clipboard: one button each. Empty project start screen (launcher) already lists recents; add
"Open the sample" once the sample exists.

- Rule: an empty state names at most one command and one gesture. Text from locale with `{key:id}`.
- Pure helper `emptyState(panel, state) -> { textKey, commandId }`, node-tested; DOM in each panel.
- Effort: S (strings exist; add button + key token). Sample project: L, blocked on recording.
- Files: `ui/empty-state.js` (new), `ui/transcript.js`, `ui/candidates-panel.js`,
  `ui/markers-panel.js`, `ui/clipboard-panel.js`, `ui/lanes.js`, `src/kuulas/locales/{en,fi}.json`.
- Clutter for experts: none; empty states vanish once there is content.
- Deps: the `{key:}` fill for locale strings (defects above).

### 2. Contextual "you can also" line in the status bar (key promoter)

Prior art: IntelliJ "Key Promoter X", VS Code palette showing keys, macOS menu flash. The strongest
teaching moment for a keyboard tool is "you just did that with the mouse; the key is X".

- Trigger: a command that has a key was run by **menu, context menu, button or palette**. The
  `#keyhints` slot shows for ~6 s: "Split: S. Also: Split all tracks Shift+S" (the command's key,
  then at most one related command from a curated `related` list of ids).
- Second trigger (rarer): after a command, one "next step" id (`Split` -> `Merge`; `Delete words`
  -> `Find removed`). Ids only, in one data table; text comes from labels and keys.
- Caps: each command promoted at most 3 times; never again once the user ran it by key twice; at most
  one line per 2 minutes; never during playback or recording; never over an error notice.
- Off switch: View > Options > "Show key reminders" (default on); Help > "Reset reminders".
  Counts in prefs (this computer only, `ui/prefs.js`), like recent commands.
- Pure model `ui/key-promoter.js`: `(event, counts, now) -> line | null`, node-tested; the dispatcher
  already knows the source of each run (needed for menu flash).
- Effort: M. Files: `ui/key-promoter.js` (new), `ui/hints.js`, `ui/app.js` (dispatch hook),
  `ui/menu-model.js` (two items), `ui/preferences-model.js`, locales.
- Clutter: low; an expert who uses keys never triggers it, and it is one line in an existing slot.
- Deps: none. Owner question 1.

### 3. Hover tips and key affordances on transport, lanes, clip labels

- Wire `ui/tip-model.js`: one delegated listener on `[data-cmd]` elements; tip = label + key + hint
  (`cmd.*.hint`), 600 ms delay, suppressed after press. Replaces `title` on command buttons.
- Mark every command button with `data-cmd="<id>"`; the tip, `aria-keyshortcuts` and the
  menu-coverage test all read it. A test fails when a `data-cmd` id is not a registry command.
- Lanes: track header buttons (mute, solo, role, bus) and the new drag handle get `data-cmd`.
  Clip label: tip on the label names the clip's right-click menu ("Right-click for clip
  commands") once per session, then label + mute/fade state only.
- Transport: play, record, loop, speed slider; the speed slider tip names fast/slow/shuttle keys.
- Effort: M (model done; wiring + ~40 buttons). Files: `ui/tip-model.js`, `ui/tip.js` (new DOM),
  `ui/index.html`, `ui/transport.js`, `ui/tracks.js`, `ui/clip-label.js`, `ui/style.css`,
  `ui/tests/tip-wiring.test.js` (new).
- Clutter: none until hover; respects motion setting.
- Deps: none. Unblocks 4 (strip buttons reuse the tip).

### 4. Selection strip: build, small

Decision: **build**, as a row of 4–6 buttons that appears only while something is selected, in the
same slot style as the follow chip (above the lanes, right of the clock), each button showing its key.
It is not a palette: it holds no command of its own.

- Source of truth: the **first items of the right-click menu for the same target**
  (`ui/context-menu-model.js`), filtered to those with a key, capped at 6. So the strip, the context
  menu and the menus never disagree; reordering the context menu reorders the strip.
- Expected contents (by command id, from today's context menus):
  - clips: `edit.split`, `edit.remove`, `clip.mute`, fade, `edit.group`, export selection;
  - words: `transcript.delete_words`, `transcript.remove_words`, correct, `candidate.mark`,
    `transport.play_selection`;
  - range (in/out or painted): `transport.play_selection`, `transport.loop_selection`, `edit.remove`,
    region from selection, export range.
  - Last button "More…" opens that same context menu at the strip (teaches right-click exists).
- Off switch: View > Options > "Selection strip" (default on); the strip never moves the layout
  (overlay row, fixed height) so turning it on/off does not shift lanes.
- Effort: M. Files: `ui/selection-strip.js` (new, model + DOM), `ui/context-menu-model.js`
  (export a "primary" slice), `ui/app.js`, `ui/index.html`, `ui/style.css`, locales (1–2 strings).
- Clutter: medium; that is why it is overlay, capped, and switchable. Owner question 2.
- Deps: 3 (button tips), uncommitted context-menu work merged first.

### 5. Help > Getting started and "What's new / things to try"

- Getting started exists as a submenu. Add, in order: one help topic `start.md` already exists; link
  Getting started's last item to it, and later to the tour (R60). No new menu items beyond that.
- **What's new, generated:** ship `ui/help/commands-by-version.json` produced by a script from the
  registry at release time (`version -> [command ids added]`, a diff of `DEFAULT_KEYMAP` ids between
  tags). On launch, if the user's last-seen version is older, Help > "What's new" lists the new
  commands: label, key, menu path (from `findItem`), Run button. No hand-written prose; the
  CHANGELOG stays the prose record.
- **Things to try:** a list of the "Regular (second week)" commands from `docs/design/MENUS.md`, as
  ids in one data file, minus those the user has run (recent/usage counts in prefs). Shows label,
  key, menu path, Run. Shown in the Help panel, not as a pop-up.
- Effort: S for the topic link; M for both lists (script + panel view + tests).
- Files: `scripts/commands_by_version.py` (new), `ui/help/commands-by-version.json` (generated),
  `ui/help/try.json` (ids), `ui/help-panel.js`, `ui/menu-model.js` (Help > What's new,
  Help > Things to try), `ui/recent-commands.js` (usage counts), locales.
- Clutter: none (inside Help).
- Deps: usage counts shared with item 2.

### 6. Discoverable by search (palette and Help search)

- Test that **every** registry command is found by its own label in both languages and by at least
  one synonym for the ~60 "first hour" + "regular" commands (extend
  `ui/tests/command-synonyms.test.js` with a coverage list, not prose).
- Help topics in palette results (GUI-DESIGN 26 "not yet": palette search of topics): already
  `TOPIC_LIMIT` in `command-search.js`; check the palette shows them, not only Help search.
- Search by key: typing a key chord in the palette ("Shift+S", "vaihto s") finds the command bound
  to it. Parses with the same formatter, so it follows remaps.
- Synonym sweep from real queries: log zero-result queries locally (prefs, last 50) and show them in
  Help > Performance report so the owner can paste them into `command-synonyms.js`.
- Effort: S (tests + key search) to M (zero-result log).
- Files: `ui/command-search.js`, `ui/command-synonyms.js`, `ui/palette.js`, `ui/perf-model.js`,
  `ui/tests/command-search.test.js`.
- Clutter: none. Deps: none.

### 7. Learn the keys: cheat sheet, not a new mode

- Keep the generated cheat sheet (`help.keys`) as the one key reference; no hand-written key tables
  in help text (lint test below).
- Add to it: filter "Not used yet" (from usage counts), "Show in menu" per row (Alt+Enter, like Help
  search), and a printable/export view (HTML written next to the project or to Downloads).
- A keyboard-picture view (Finnish layout, keys coloured by context) is **parked**: L effort, layout
  data per locale, low payoff over the filtered list.
- Lint test: no locale string matches `(Cmd|Ctrl|Alt|Shift|Mod)\+` or `Press [A-Z]\b` outside an
  allow-list; help bodies must use `{key:}`. Fails today on 27 strings (fix as part of item 1).
- Effort: S (filter + lint) / M (print view).
- Files: `ui/cheatsheet.js`, `ui/tests/no-literal-keys.test.js` (new), locales, `ui/help/*/*.md`.
- Clutter: none. Deps: usage counts (item 2/5).

### 8. How to measure / verify

No telemetry leaves the machine. Verification is tests plus a 10-minute owner script.

- Tests (CI): no literal keys in strings; every `data-cmd` is a real command; every command with a
  key shows that key in menus, tips, strip and cheat sheet (one test over the four renderers);
  synonym coverage list; key-promoter caps (3 times, 2 min, off switch, never during playback).
- Local counts (prefs only): per command, runs by key vs by mouse/menu. Help > Performance report
  shows "Run by mouse most: …" so the owner sees what is not yet learned.
- Owner, 10 minutes, fresh settings (Help > Reset reminders):
  1. Open an empty project: is the next step obvious in each panel without the docs? (1 min)
  2. Import via the empty-state button; Split via the Clip menu: does the status line name the key? (2)
  3. Select a clip, then words: does the strip show the right 4–6 with keys? Turn it off. (2)
  4. Hover play, record, a track's mute, a clip label: key in every tip? (1)
  5. Palette: type "poista", "razor", "Shift+S", "vaihda kieli": right command each time? (2)
  6. `?` sheet: filter "Not used yet"; remap one key in Keymap and check tip + strip + sheet follow. (2)

---

## Recommended order (first three)

1. **Literal-key cleanup + lint test + empty-state buttons (items 1, 7 lint).** S. Fixes a real
   drift bug (markers "Press M") and is the base every other surface uses.
2. **Hover tips wired with `data-cmd` (item 3).** M. The model exists; the owner already chose hover
   tips (Q23); the strip reuses it.
3. **Key promoter line (item 2).** M. Highest teaching value for a keyboard-first tool, uses an
   existing slot, invisible to people who already use keys.

Then: selection strip (4), search coverage (6), what's new / things to try (5), cheat sheet filter (7).

## Open questions for the owner

1. Key promoter (item 2) is a post-action tip in the status line, capped and switchable. Does that fit
   your Q23 "hover tips, not timed tips", or should it stay off by default?
2. Selection strip: build it (default on, switchable), or rely on right-click menus + key promoter?
3. Strip position: above the lanes beside the clock, or in the status bar beside the key hints?
4. Usage counts (runs by key vs mouse) stored on this computer: fine to keep, for "Not used yet" and
   "Things to try"?
5. "What's new" on first launch after an update: a quiet notice chip ("12 new commands"), or only in
   the Help menu?
