# Forms: one grid for every dialog and panel

Owner, 2026-10-20: "go through all panels and modal windows and make sure that texts and
input fields are aligned nicely so it's not all scattershot." This page is the rule. It uses
the tokens in `ui/tokens.css` ("Forms") and the classes in `ui/style.css` (section "forms");
`BUTTONS.md` has the buttons. `ui/tests/form-layout.test.js` pins the grid and scans
`ui/*.js` for rows built the old, per-dialog way.

## The grid

Every form row has two columns:

| Column | Width | Holds |
|---|---|---|
| label | `--form-label-w` (dialogs: 200 px comfortable, 168 px compact); in side panels and floating panels `--form-label-w-panel` (128 / 112 px) | the label, `.form-label` |
| field | the rest (`minmax(0, 1fr)`) | the control, then its help and message lines |

- The columns are `--form-col-gap` apart (12 px comfortable, 8 px compact).
- The widths are fixed, not fractions of the box: every row, every section and every nested
  card in one dialog puts its fields on the same x. A 2fr/3fr split per box was the
  scattershot (each box was a different width, so each section had its own field edge).
- Rows are `--row-gap` apart; sections `--section-gap` (the density tokens, GUI-DESIGN.md 16).

```
| label column (--form-label-w) | gap | field column                         |
| Target loudness (LUFS)        |     | [   -16 ] [-16 Podcast] [-14] [-23]  |
|                               |     | help text, at the field's left edge  |
|                               |     | [x] Leave room for an ad break       |
|                               |     |     its description, under its text  |
```

## Classes

| Class | What | Rule |
|---|---|---|
| `.form-grid` | the form (or a panel's block of rows) | grid, `--row-gap` between children |
| `.form-section` + `.form-heading` | a titled group | heading: `--text-sm`, strong, secondary, a divider under it |
| `.form-row` | one row | `<label class="form-row"><span class="form-label">…</span><input></label>`, or a `div.form-row` with a `label.form-label[for]` |
| `.form-label` | the label cell | as tall as a control (`--control-h`), text centred on it |
| `.form-field` | an optional wrapper for the field column | grid, `--form-help-gap` between control, message, help |
| `.form-help` | help under a field | `--text-xs`, tertiary; always in the field column |
| `.form-msg` | a validation or error message | `--text-xs`, `--danger-text`; under the field, before the help; empty = no row |
| `.form-note` | a note about the whole form or section | `--text-sm`, secondary, full width from the form's left edge |
| `.form-inline` | several controls on one line (field + Choose…, slider + value) | flex, `--space-3` |
| `.form-num` / `input[type=number]` | a number | `--form-num-w` wide, right-aligned, tabular figures |
| `.silence-slider-row` | a `.form-row` with a slider (Auto-Silence panel) | label and a small number (7ch) on one line; the slider on its own line, full width (`grid-column: 1 / -1`, 28 px tall); help under it in the field column |
| `.form-readout` | a value shown next to a slider | right-aligned, tabular, `--text` |
| `.form-readonly` | a value that is not edited | as tall as a control, left-aligned |
| `.check-row` | a checkbox with its text (and description) | box on the field column's left edge; see below |
| `.form-choices` / `.form-choice` | one of n (radios) or a list of boxes in the field column | box on the first line; lines below align with the text |
| `.form-card` | a card inside a form (the automixer's option groups) | gives its padding back to the label column |
| `.form-sub` | fields that depend on a check above them | indented with a rule; gives the indent back |
| `.form-fieldset` | a `<fieldset>` on the grid | the legend (`.form-label`) takes the label column |
| `.form-actions` | buttons inside a form (links to other dialogs) | wraps, from the left edge |
| `.footer-start` | a footer action that keeps the dialog open | see "Footers" |

Old per-dialog classes (`automix-row`, `silence-hint`, `inspector-field`, …) may stay on an
element as a hook, but only next to their shared class; the test lists them (`LEGACY`).

## Rules

1. **Help belongs to its field.** Help text and messages go in the field column under the
   control (`.form-help`, `.form-msg`), never at the dialog's left edge. A sentence about the
   whole section is a `.form-note` at the left edge, above or below the rows.
2. **Check rows sit on the field column.** A check that is a setting of its own
   (`.check-row`): the box at the field column's left edge, its text after it
   (`--check-gap`), its description under the text. A yes/no that answers the row's label
   (Preferences "Confirm before sync", inspector "Mute track") is a `.form-row` with the box
   alone in the field column. `.check-row.form-wide` drops the label column: only for a check
   that stands alone (a filter in a panel, "Do not ask again" in a short notice).
3. **Nesting keeps the field edge.** A `.form-card` or `.form-sub` indents its content and
   subtracts the indent from the label column (`--form-card-indent`, `--form-sub-indent`), so
   the field column does not move. Only the right edge comes in by the card's padding.
4. **One control height.** Inputs, selects and the slider row are `--control-h`; a label's
   single line is centred on the control's text line, so label and value share a baseline.
5. **Numbers** are `--form-num-w` wide and right-aligned; the unit goes in the label in
   parentheses ("Fade in (ms)", "Häivytys sisään (ms)"), not after the field. A slider's value
   is a `.form-readout` at the end of the line.
6. **Long labels wrap; they never push the field.** The label column is fixed, so a long
   Finnish label wraps (hyphenated by `lang`) to two lines inside it. A label that needs three
   lines is too long: shorten it and put the rest in the help text.
7. **Tables are not forms.** Several controls per line for each item (the record view's
   channel list, export's track list) is a full-width block under a `.form-heading`, or sits
   whole in the field column (export's track list under "What").
8. **Hidden is gone.** `[hidden]` rows, messages and helps take no space (the `.form-grid`
   rule), and an empty `.form-msg` takes no row.

## Dialogs

- `dialog.cheatsheet`: padding `--space-6`, radius `--radius-lg`; width 640 px for a form
  (`.automix-dialog`), 560 px for the record view.
- Order: the title (`h2`, `--text-lg`, `--space-5` under it), an optional intro `.form-note`,
  the form (`.form-grid`), the footer.
- **Footers** (`.cheatsheet-footer`): right-aligned block buttons; Cancel / Close, then the
  primary **last**. Actions that keep the dialog open (Reset, Preview, Copy, Save, Choose
  folder, Stop) carry `.footer-start` and sit at the left edge; the first button after them
  is pushed right. A select in a footer (the record view's stop mode) is a `.footer-start`.
  The test checks that the primary is appended last in every footer.

## Panels

- Side panels set `--form-label-w: var(--form-label-w-panel)`, so the same classes give a
  narrower label column; the floating import panel and placeholder editor do too.
- Panel padding is `--pad-panel`; the action bar (`.actionbar`) is the one row of block
  buttons at the top (BUTTONS.md); settings rows under it are `.form-row`s in a `.form-grid`
  (the clipboard's paste choices, the import panel's "next time" choices).
- The inspector's rows are `.form-row`s (`field()` in `inspector-track.js`); its sections are
  `<details>` with the summary as the section heading.

## Under 520 px

The label goes above its field (one column) and check rows lose their indent.

## Where it is used (2026-10-20)

Automix, Export (mix and tracks), Preferences, Send a copy, Locate media, the Auto-Silence
options panel, Colab settings / upload notice / sign-in, New and Open project, Statistics (footer,
note), Performance report, Record view (setup rows, footer), Sync confirm (footer), the
placeholder editor, the inspector (track, bus and clip sections), the clipboard panel (paste
choices, keep-count field, view switch), the candidates filter, the import panel. The cheat
sheet, markers, history and help panels have no form rows: their headers are the shared
`.actionbar` and `.cheatsheet-footer`. The launcher page (`launcher_page.py`) has buttons
only and copies the button section of `style.css`, not this one.
