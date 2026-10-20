# Buttons: the rulebook

Owner, 2026-10-20: "Make EVERY appropriate button follow the design rulebook!" This page is
that rulebook. It uses the tokens in `ui/tokens.css` and the classes in `ui/style.css`
(section "buttons and chips"); `GUI-DESIGN.md` 8.4 has the state table it extends.
`ui/tests/button-rulebook.test.js` enforces it: every `<button>` in `ui/*.js`,
`ui/index.html` and `src/kuulas/launcher_page.py` carries `.button` or is one of the
special widgets listed at the end, with a reason.

## Kinds

Every button is `.button` plus at most one kind, and optionally `.icon`, `.small`,
`.danger` or a toggle state. Pick by where the button sits, not by how loud it should look.

| Kind | Classes | Looks | Use for |
|---|---|---|---|
| Primary | `.button.primary` | `--button-primary-bg` (accent) fill, `--button-primary-text`, weight strong | the one main action of a dialog, panel or view; at most one per group. Play is the window's primary (`.play`). |
| Secondary | `.button` | `--button-bg` body, 1 px `--button-border` | every other action: dialogs' Cancel when not a block, toast and floating-panel actions (Show in Finder, Undo, Cancel), inline actions in a panel |
| Tertiary (ghost) | `.button.ghost` | no fill, no border at rest; hover shows the whole hit area: `--button-hover-bg` and `--button-hover-border` | toolbars and the status bar, a close ×, row actions in lists until the block row lands (see "Lists") |
| Icon | `.button.icon` (+ `.ghost` in toolbars) | square, `--control-h` wide, no padding; `aria-label` and `title` required | ±, ↑ ↓, ×; a glyph alone only when its meaning is universal |
| Block | `.button.block` (+ `.primary`) | 76 px square, the icon over the label, `--radius-sm`; secondary blocks have Record's raised body (`--surface-raised`, `--border-strong`) | panel action bars (one bar, at the top), dialog footers, the transcript offer |
| Destructive | add `.danger` | a secondary (or ghost) at rest; on hover `--danger-text`, `--danger` border, `--danger-subtle` fill | Delete, Remove, Clear. Undo brings it back, so it does not shout at rest; a confirm step (only for what undo cannot restore) shows danger at rest. |
| Toggle | any kind + `aria-pressed` | on = `--surface-active` fill and `--border-strong` border (`.button[aria-pressed="true"]`) | on/off and one-of-n choices (Loop, LUFS presets, clipboard view). The label does not change; the state is in `aria-pressed`. |

## Sizes and hit targets

- Default height `--control-h` (32 px comfortable, 22 px compact).
- Top bar: `--control-h-lg` (40 px) with an `::after` that makes the hit target
  `--target-min` (44 px).
- `.small`: `--control-h-sm` (28 px), only for actions inside reading text (help: Run, Show me).
- Block: 76 px square, one size; the label wraps inside, it never widens the block.
- Status bar: the ghost shrinks to the bar (`--statusbar-h` − 8 px); still a full box on hover.
- Never smaller than 24 px in either direction (WCAG 2.5.8), compact included.

## States

| State | Rule |
|---|---|
| hover | secondary: `--button-hover-bg`, border `--button-hover-border`; ghost: the same (its hit area appears); primary: `--button-primary-hover-bg` |
| active (pressed) | `--button-active-bg` |
| focus | `:focus-visible` ring: `--focus-width` (2 px) `--focus-ring`, offset `--focus-offset`. Never removed. |
| disabled | `disabled` attribute; text `--text-disabled`, no hover, default cursor. Prefer hiding a button that can never apply here. |
| on (toggle) | `aria-pressed="true"`: `--surface-active` + `--border-strong` |

## Words and order

- Sentence case, a verb first: "Show in Finder", "Näytä Finderissä", "Paste again".
  No trailing period. A label that opens a dialog ends in "…".
- The label is a message key with English and Finnish in the same commit (R39).
- Inline buttons: icon left of the label (`data-icon`, drawn by `ui/icons.js`). Blocks:
  icon over the label. Use an icon from `ICONS`; no emoji.
- Key hints go in `title` ("Split · B") or a `kbd` inside the button (`.keyed`), never in
  the label text.
- In a group the primary comes last (right): Cancel, then Start. Close × is the last item
  of a toast or floating panel's head.

## Where each kind goes

- **Dialogs** (`.cheatsheet-footer`): block buttons; the confirming action is
  `.block.primary` and last; Cancel / Close is a secondary block with the `close` icon.
  Actions that keep the dialog open (Reset, Preview, Copy, Choose folder) carry
  `.footer-start` and sit at the left edge (`FORMS.md`, "Footers").
- **Side panels**: one action bar (`.actionbar`) at the top of block buttons.
- **Toasts and floating panels** (notice, import panel, placeholder editor): secondary
  buttons at `--control-h`, a primary only for a real decision (Save); the close is a
  `.button.ghost.icon` ×.
- **Toolbars and the status bar**: ghosts; icon buttons for ± and arrows.
- **Lists** (clipboard, markers): the row body is the row's button (`.clip-main`); the row's
  actions sit in `.clip-actions`. The clipboard is moving its row actions to square block
  buttons with a play/stop toggle (in flight, 2026-10-20); when that lands it is the rule
  for every list, and the markers rows follow it (they share `.clip-entry` / `.clip-actions`).
  Until then row actions are ghosts, Delete with `.danger`.

## Special widgets (not `.button`)

These have their own look and their own row in `GUI-DESIGN.md`. A new one needs a reason
here and in `SPECIAL` in `ui/tests/button-rulebook.test.js`.

| Class | What | Why not `.button` |
|---|---|---|
| `.play` | Play and Record in the transport corner | the one Play shape |
| `.chip` | status chips (record, speed, waveform gain, scope) | a pill showing a state, clicking resets it |
| `.menu-title` | menu bar titles | `role=menuitem`, menu look |
| `.menu-item` | menu and context-menu rows | `role=menuitem` |
| `.side-tab` | the sidebar tab strip | `role=tab` |
| `.ms-button` | the track header M / S toggles | `--control-h-sm`, neutral / amber fill |
| `.track-name` | the track name | a label; double-click renames |
| `.tag` | speech / music kind tag | a tag in the header |
| `.bus-chevron` | the bus disclosure chevron | disclosure |
| `.role-badge` | the "!" flag on a track whose kind differs from its bus's role | a status flag in the header; click matches the role |
| `.bus-reapply` | "Reapply" in a bus header while a track differs from the bus role | a header-sized text button, only shown when needed |
| `.mrow` | Alku / Loppu / Pituus in the marks corner | a label and a time on one line |
| `.lm-clip` | level meter clip light | an indicator |
| `.clip-main` | a list entry's body (clipboard, markers) | the row is the button |
| `.automix-group-head` | a disclosure header in the automix dialog | the whole row toggles the group; chevron, title, badge |
| `.clip-project` | a project heading in the clipboard list | a disclosure row |
| `.source-row` | a source row in the inspector | the row is the button |
| `.tx-pause` | a pause marker in the transcript | inline in text, not a tab stop |
| `.record-clip` | the record meter's clip light | an indicator |
| `.record-stop` | hold-to-stop in the record view | a ring that fills while held |
| `.cmd-search-show` | the palette row's "show in menu" | pointer-only, `aria-hidden` |
| `.row` | a launcher list row | the row is the button |

## Inventory (2026-10-20)

C = conforms, F = fixed in this change, D = deferred (reason given), S = special widget.

| Where | Button(s) | Class | Status |
|---|---|---|---|
| Transport corner | Play, Record | `.play` | S |
| Transport corner | Loop | ghost icon toggle | C |
| Marks corner | Alku / Loppu / Pituus | `.mrow` | S |
| Top bar | record, speed, waveform-gain chips | `.chip` | S |
| Menu bar, context menus | titles, items | `.menu-title`, `.menu-item` | S |
| Sidebar | tabs | `.side-tab` | S |
| Status bar | close/wide view, Help, View | was `.button` restyled to a ghost by place | F: `.button.ghost` in the markup; hover shows the border |
| Status bar | scope chip, level clip | `.chip`, `.lm-clip` | S |
| View menu | zoom ±, lanes ± | `.button.icon` | C |
| View menu | Fit, Follow, Theme | `.button` | C |
| Toast (notice) | Show in Finder / Cancel (`notice-action`) | was ghost: text on a faint hover | F: secondary |
| Toast | Undo | was ghost | F: secondary with the undo icon |
| Toast | × | `.button.ghost.icon` | C (ghost hover now shows the border) |
| Import panel | × | ghost icon | C |
| Import panel | mono Yes / Sequence | `.button` | C |
| Import panel | mono No, Undo | was ghost | F: secondary |
| Placeholder editor | Save, Cancel | none (bare browser buttons) | F: Save `.primary` last, Cancel secondary |
| Automix dialog | choose folder, Close, Start | blocks | C |
| Automix dialog | LUFS presets | `.button` toggles | C |
| Export dialog | All, None, Cancel, Start | blocks | C |
| Colab, Preferences, Send a copy, Locate, Silence, New project, Cheat sheet | footers | blocks | C |
| Performance dialog | Start, Stop, Close | was `.button` | F: blocks (play / close icons) |
| Statistics dialog | Copy, Save, Close | was `.button` | F: blocks (save / close icons) |
| Sync confirm | Cancel, Confirm | was `.button` | F: blocks (close / check icons) |
| Record view | Hide / Close | was `.button` | F: block |
| Record view | Record | `.button.record-button` | C |
| Record view | clip light, hold-to-stop | `.record-clip`, `.record-stop` | S |
| History panel | Undo, Redo, Restore, Older | blocks | C |
| Candidates panel | Find, Preview, Delete (primary), Cut, Keep | blocks | C (Delete is the panel's primary: what the panel is for, undoable) |
| Markers panel | action bar | blocks | C |
| Markers panel | row Rename, Chapter (toggle), Delete | ghost | D: list row actions follow the clipboard block row once it lands (shared CSS, owned by the clipboard work); Delete now `.danger` (F) |
| Markers panel | row body, left-off, drift rows | `.clip-main` | S |
| Clipboard panel | chip actions (Play, Paste again, Rename, Delete), star | ghost | D: being restyled by the clipboard work (agent ac12d3a45c2f40e40) into blocks; must follow this page: Delete `.danger`, star and play/stop are toggles with `aria-pressed` |
| Clipboard panel | This project / Shared / Other projects | `.button.clip-view` toggles | C |
| Clipboard panel | Clear old items | block with trash icon | C (should add `.danger`: clipboard work) |
| Clipboard panel | project headings | `.clip-project` | S |
| Inspector | source rows | `.source-row` | S |
| Track headers | M, S, name, kind tag, bus chevron | special | S |
| Transcript | Follow | `.button` | C |
| Transcript | find ↑ ↓ | was `.button` with a glyph | F: `.button.icon` |
| Transcript | find × | was `.button` | F: `.button.ghost.icon` (like the toast's) |
| Transcript | Transcribe… offer | blocks | C |
| Transcript | selection pop-up actions | `.button.keyed` | C |
| Transcript | pause markers | `.tx-pause` | S |
| Help panel | Back | ghost small | C |
| Help panel | × | ghost icon | C |
| Help topics | Run, Show me | `.button.small` (the class had no rule) | F: `.small` now defined (`--control-h-sm`) |
| Command search | show in menu | `.cmd-search-show` | S |
| Launcher page | Open (primary), New | `.button` | C |
| Launcher page | project rows | `.row` | S |
