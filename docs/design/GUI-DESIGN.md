# kuulas GUI design

The design specification for the kuulas editor window. It is written for the
implementer who picks up one component at a time: every size, colour, state
and rule is here, and nothing should need guessing. Where a choice was open
in `docs/PLAN.md`, it is made here with a one-line reason; the owner's open
questions are at the end.

Owner of this document: the design work package (branch `gui-design`, 17.10.2026).
Requirements: `ROADMAP.md` (R1–R55). Work packages: `docs/PLAN.md` (WP4–WP8,
WP18, WP19, WP24, WP26, WP28, WP43, WP44).

## 0. Sources of truth, in order

| What | Where | Rule |
|---|---|---|
| Every colour, size, duration | `ui/tokens.css` | The only file with colour values. Three layers (section 4.1). |
| Every visual signal on a clip, lane or group | `ui/grammar.js` | The registry: channel, priority, tokens, non-colour twin. Canvas and worker code read colours through it (`resolvePalette`). |
| What it looks like | `docs/design/prototype/index.html` | Clickable, offline, fake data, no audio. Embeds copies of `tokens.css` and `grammar.js` (`node docs/design/sync-tokens.mjs` refreshes them; a test fails if they drift). |
| Pictures | `docs/design/screenshots/` | Every prototype screen in both themes, made by `sh docs/design/screenshots.sh`. `app-*.png` are the real editor. |
| Why and how | this file | Prose, tables, procedures. |

If this file and the code disagree, the code (tokens, registry, tests) wins
and this file is fixed in the same commit.

**View the prototype:** open `docs/design/prototype/index.html` in a browser
(double-click it; no server needed). The black bar at the top switches screen,
theme, language and density. URL parameters: `?screen=main|transcript|history|candidates|palette|focus|buses|empty|error|gallery&theme=light|dark|system&lang=en|fi&density=comfortable|compact&clean=1`.

## 1. Design principles

1. **Calm by default; loud only when something is wrong or unusual.** Long
   sessions with tired eyes. So we draw a state only when it differs from the
   safe default (the gain line appears when a clip's gain is not 0 dB; "Group
   editing off" appears only when it is off), and we never decorate: no
   gradients, no glow, no coloured panel backgrounds.
2. **The audio is the brightest thing on screen.** Chrome is neutral grey;
   colour belongs to waveforms (who speaks) and to warnings. So panels use
   `--surface-*` only, and hue is never used for a button or a panel header.
3. **One channel, one meaning** (section 5). Hue says who; tone says which
   file; opacity says how audible; outline weight says selected; dashes say
   "not real yet"; hatch says "absent or may be absent". So a new feature
   picks a free channel or reuses one with the same meaning, never a colour
   "because it looks nice".
4. **Never colour alone.** Every colour signal has a twin in shape, pattern or
   text (registry field `twin`, test-enforced). So a colour-blind user or a
   greyscale screenshot loses nothing.
5. **Keyboard first, mouse welcome, keys visible.** Every action has a key
   (WP5), every key is shown where the action is (tooltip, palette, status bar
   hints). So no feature ships with a mouse-only path, and the status bar
   always says what Enter and Backspace will do *here*.
6. **Undo, don't ask.** Edits apply at once and say what they did, with Undo
   in the message. So there are no "Are you sure?" dialogs for anything
   undoable; confirmation is only for what history cannot bring back (closing
   while a recording runs, deleting media from disk).
7. **Snappy, then right.** Edits show a provisional result within a frame and
   the engine confirms within 50 ms. So nothing waits on the server to move,
   and a spinner appears only after 400 ms (jobs, never edits).
8. **Finnish is the long language.** Strings run about 30 % longer. So every
   label has room for +40 %, truncates with an ellipsis and a tooltip, and no
   layout depends on the English width (checked with `lang=fi` screenshots).

## 2. The main window

```
┌ top bar 44 ─ project/edit │ ▶ Play  0:12:34.567  [1.5×] [Group editing off] … jobs  ↶ ↷  Import Export  ⌘K ┐
├ heads 248 ────────────────┬ overview 20 ──────────────────────────────────────┬ sidebar 320 ──────────┤
│ (spacer = overview+ruler) │ ruler 24                                          │ tabs 36               │
│ ▾ [A] Voices      M S     │ bus row (band)                                    │ Inspector │ History │ │
│ ▌Anna        A▾  M S      │ lane 56: clips, half waveforms                    │ Candidates │ Clip bin│
│ ▌Ville       A▾  M S      │ lane 56                                           │                       │
│ ▸ [B] Music (1)   M S     │ collapsed bus: summed waveform                    │ panel body            │
├───────────────────────────┴───────────────────────────────────────────────────┤                       │
│ transcript dock 30vh (min 120, max 60 %)                                      │ action bar (sticky)   │
├ status bar 26: − Close·30 s + Fit │ waveform  lanes  follow │ key hints … saved · theme ┴───────────────┘
```

| Region | Size (comfortable / compact) | Min / max | Resize | Always visible |
|---|---|---|---|---|
| Top bar | 44 / 38 px | fixed | no | yes |
| Project block (top-left) | width = track header column | follows the column | with the column | yes |
| Track header column | 248 / 216 px (`--heads-w`) | 180 / 360 | drag its right edge (planned) | yes |
| Overview strip | 20 px | fixed | no | yes, when the edit has clips |
| Ruler | 24 px (`lanes.js RULER_HEIGHT`) | fixed | no | yes |
| Track lane | 56 / 40 px (`DEFAULT_LANE`) | 24 / 160 | Shift+= / Shift+- all; drag a lane's bottom edge for one | — |
| Bus header row | 44 px (`BUS_HEIGHT`), lane height when collapsed | — | — | — |
| Focus-mode strip | 16 px | — | — | in focus mode |
| Sidebar | 320 / 280 px | 260 / 480 | drag its left edge (planned); hide from the palette | yes (hideable) |
| Transcript dock | 30 vh | 120 px / 60 % | drag its top edge (planned); collapse to its 34 px header | yes (collapsible) |
| Status bar | 26 / 22 px | fixed | no | yes |

Rules:

- One screen, no page scroll. The window's minimum is 960 × 600 px. Below
  1100 px wide the status-bar key hints hide; below 960 px the sidebar becomes
  an overlay opened from its tab (planned, not built).
- Docks are separated by 1 px lines (`--frame-gap`), never by shadows.
- The project block above the headers keeps the transport aligned with the
  timeline's left edge: the eye runs straight down from Play to the playhead.

## 3. Panels and components

Each entry: purpose · contents · states. File names are in the component
inventory (section 11).

### 3.1 Top bar

- **Project block:** project name (600) and below it the open edit with its
  length ("Main edit · 58:41", WP21); click or Mod+O opens the edit switcher.
  Today the app shows "kuulas" (no project name in the API yet).
- **Transport:** Play/Stop is the one accent-filled button in the window
  (`--button-primary-bg`), with its key chip inside. The timecode is 20 px,
  600, tabular numerals, `h:mm:ss.mmm` with the milliseconds in
  `--text-secondary`; Finnish uses the decimal comma (`0:12:34,567`).
- **Mode chips** (only when not default, amber `.chip.warn` unless noted):
  speed ≠ 1× ("1.5×", key `.`), "Group editing off" (E), "Solo: Ville"
  (Shift+S), "Focus: Ville · Esc" (neutral `.chip.info`), A/B "B −2.3 dB
  matched" (neutral), connection lost "Reconnecting…" (`.chip.danger`, the
  reassurance "everything up to your last edit is saved" in its tooltip and
  in the status bar). They never truncate; if space runs out the job chip
  shortens to "2/3" first.
- **Jobs chip:** progress ring + "Transcribing 2 of 3"; click opens a 300 px
  popover: one row per job with a 4 px bar, percent, time left, Cancel; a
  failed job shows its error in `--danger-text` and Retry. Hidden when no jobs.
- **Undo/Redo:** ghost icon buttons (tooltips "Undo · ⌘Z"). Import (Mod+I in
  the browser, see 8.3), Export (Mod+E), Commands ⌘K (opens the palette; for
  mouse users to discover it).

States: empty project → Play and Undo disabled, Import becomes primary.

### 3.2 Track headers and bus headers

**Track header** (lane height; two rows of 20 px when ≥ 44 px, one row below):

- row 1: role icon (mic = speech, two mics = speech mix, note = music; the role
  name is the tooltip and the accessible name) · name (600, ellipsis,
  double-click renames) · bus picker (the bus letter, 46 px, `A ▾`; "–" for
  none) · M · S
- row 2: gain slider (−60…+12 dB, value "−1.5 dB" right-aligned, tabular) ·
  pan slider (76 px, "L 10" / "C" / "R 10"; Finnish "V/K/O")
- left edge: the **bus spine** (4 px, full height, bus colour) and beside it
  the **track pill** (3 × 22 px, rounded, the track's hue). Different shapes,
  so bus and speaker never fight.
- current track (↑/↓ cursor): background `--header-bg-current`, the same tint
  across its lane.
- muted track: M filled neutral (`--mute-on-bg`), its clips at
  `--signal-unheard-opacity`. Not heard because another track is soloed: name
  and controls at 55 %, M dashed, tooltip "not heard: solo".
- solo: S filled amber, plus the "Solo: …" chip in the top bar.

**Bus header** (a group header, like a folder; 44 px, two rows): disclosure
chevron (collapse / expand, Alt+← / Alt+→ on the current track's bus) · letter
badge (A, B, …: 18 px square, 1.5 px border in the bus colour, letter in
`--bus-N-text`) · name (600, bus text colour) · member count when collapsed ·
M · S; row 2: gain and pan. Details in section 6.

### 3.3 Ruler and overview

- **Ruler:** `--ruler-bg`, labels 11 px monospace in `--ruler-text` every
  ≥ 80 px (1-2-5 steps, `ruler.js`), major ticks 9 px, minor 4 px in
  `--ruler-tick`. Flags live in the ruler: in/out (accent triangles pointing
  inwards), candidates ("cut? 2.4 s" on a `--signal-candidate-fill` band with a
  3 px top edge), markers and chapters (WP19h: a notch and the name). A flag
  hides the time labels under it rather than overlapping them.
- The playhead's cap is a 11 px pentagon in `--playhead`; the start of the last
  play is a hollow triangle in `--play-start` (where Stop-and-return would go).
- **Overview strip:** one thin row per track in the track's wave colour at 60 %
  (25 % when muted), open candidates as 2 px ticks, the visible part as a box
  (1.5 px accent outline, `--selection-range` fill), the playhead as a 1 px
  line. Click or drag moves the view.

### 3.4 Timeline lanes

See section 7 (drawing) and section 5 (signals). Lane background
`--lane-bg`, 1 px separators `--lane-separator`. Empty project: the lanes area
shows the **drop card** (460 px max, dashed 1.5 px `--border-strong`, radius
10): import icon, "Import audio to begin", "Drop audio or video files here, or
choose them.", primary "Import… ⌘I", secondary "Open a Hindenburg session…",
the formats line in `--text-tertiary`. While files are dragged over the
window: full-window overlay, 3 px dashed accent border, "Drop audio files to
import them".

### 3.5 Transcript dock

Purpose: read and edit the conversation as text (WP7). Paragraphs in a
two-column grid: a 132 px speaker gutter (3 px left border in the track hue,
name 12/600, start time 11 px tabular, the bus badge after the time) and the
text at 15/1.65, max 72 ch. Word states:

| State | Look | Twin |
|---|---|---|
| playing now | 2 px accent underline | moves with the playhead |
| selected (one or many) | `--accent-subtle` band with a 2 px accent bottom edge, continuous across spaces | the popover above it |
| cut (muted audio) | line-through, `--text-tertiary` | strike |
| cut candidate | `--signal-candidate-fill` + wavy underline in the candidate colour | wavy line |
| low confidence | dotted underline, tertiary | dots |
| narration placeholder (WP43) | italic, dashed 1 px box, "to record · about 6 s" | dashes + text |

A word selection shows a popover 40 px above it: "Cut on all tracks ⌫",
"Mark cut ⌥D", "Correct Enter". Focus mode dims other speakers'
paragraphs to `--text-tertiary` (Alt+F hides them). Empty: "No transcript
yet." + "Transcribe Anna.wav, Ville.wav…" button + "Runs in the background;
you can keep editing." While transcribing: the same with the job's progress
bar. Error: the job's message and Retry.

### 3.6 Sidebar

Tabs (36 px): Inspector · History · Candidates (count pill) · Clip bin. When
the sidebar is narrower than 400 px, only the selected tab shows its label;
the others show their icon (tooltip and accessible name keep the label).
**The app today stacks Inspector over History** (no tab logic yet); switch to
tabs when WP8, WP17 or WP18 lands.

**Inspector** (selected clip): title block (4 px hue bar, file name 15/600,
"Ville · 11:30.0–13:50.0 · 2 min 20 s"), the bus line (badge + "Bus: Voices"
+ the file mark chip), then sections with 11/600 secondary headings: Level
(clip gain, pan; inputs 76 px right-aligned, unit after, key chip at the
end), Fades (in, out in ms), Sync (status line: chain icon + "Group 1 · in sync
with Anna, Pekka" in `--ok-text`; drift: warning icon, "312 ms behind its
group", the cause, buttons Resync R and Free from sync U), Voice (preset
select, layers as chips), Source (file, format, stored). Invalid input: 1 px
danger border + 1 px ring, message under the field with a warning icon
("Use a number from −60 to +12."), the value is not sent. Empty: "Select a
clip to see its level, fades and sync." + "Click a clip, or press Tab to move
between edits." Several clips: the fields they share, mixed values shown as
"—" (planned).

**History** (WP8): rows of 28 px: op icon, label, Helsinki time (`19.42`);
session markers as dividers with text ("Opened today 19.30 (Helsinki)");
checkpoints pinned and bold; the head row highlighted (`--accent-subtle` +
3 px accent left edge, "now"); steps after the head (redo side) tertiary;
abandoned branches indented with a corner connector, tertiary. Hovering a
row outlines it and draws its state as dashed ghost outlines on the timeline.
Sticky action bar: primary "Restore Enter" + "Restore adds a new step;
nothing is lost." Undo across a session marker shows the toast "Undid a step
from yesterday: **cut at 12:31** · Redo".

**Candidates** (WP18): summary chips ("3 open", "1 cut", "1 kept") and the
"Open only ⇧⌘D" toggle; rows of two lines: time (600, tabular), duration,
state chip (open = candidate-coloured outline; cut = struck; kept = neutral),
the transcript excerpt in quotes. The current candidate has the accent row
treatment and is drawn with 2 px edges on the timeline. Sticky action bar:
the preview diagram (2 s · skip 2.4 s · 2 s, the skip hatched), buttons
Preview, Cut (primary), Keep; keys are in the status bar hints.

**Clip bin** (WP17): designed later with WP17; until then the tab shows an
empty state naming the work package.

### 3.7 Status bar

Left to right: zoom out · the view toggle (Close/Wide, Z) · the span ("30 s")
· zoom in · Fit (Shift+Z) | waveform mode · lane height −/+ · follow mode
(amber text while paused by a manual scroll) · tab mode ("Tab: clip edges",
WP19i) | **key hints for the focused panel** (four or five, e.g. timeline:
"B split · X cut · Q W trim · D mark cut · ? all keys"; transcript: "⌫ cut
words · Enter correct · ⌥D mark · Esc timeline") | spacer | save state
("✓ All changes saved", `--ok-text`; when disconnected "Saved up to 19.58 ·
edits paused") | theme button (System → Light → Dark).

### 3.8 Messages (toasts)

Bottom centre, 16 px above the status bar, max 560 px, `--toast-bg` with
`--toast-shadow`, 3 px left edge (accent = info/success, danger = error).
Content: what happened ("Cut 2.4 s on 4 tracks") + actions (Undo ⌘Z, Change…,
Redo) + close ×. Success and info vanish after 6 s unless hovered or focused;
errors stay until closed. Errors say how to fix it ("The first 12:40 can still
be imported." · "Import the first 12:40" · "Show file"). One toast at a time;
a newer one replaces an older one of the same kind. `role="status"` for
info, `role="alert"` for errors.

### 3.9 Command palette (Mod+K)

Modal at 12 vh from the top, `min(640px, 100vw − 32px)`, radius 10,
`--shadow-dialog` over `--surface-scrim`. A 48 px search field (15 px text),
results in groups ("Recent" first when the field is empty, then by area),
34 px rows: icon, name with matched letters bold-underlined, the remembered
default in tertiary ("MP3 128 kbps · mono", WP35), key chips. Footer: "↑↓ move
· Enter run · ⌥Enter options · Esc close". Focus returns where it was.

### 3.10 Other surfaces (designed here, built with their WP)

- **Export dialog (WP11):** a 520 px dialog: format segmented control
  (WAV / FLAC / MP3), what (whole edit / selection / each track), loudness
  target, the destination with the next version name ("Pistejulkaisu v3.mp3"),
  the music-report and placeholder warnings as inline notices with "Show
  them". Enter exports with the shown settings; the plain key (Mod+E) skips
  the dialog when settings are remembered (WP35).
- **Music report (WP25):** a sheet over the sidebar width (480 px): the table
  (order, title, artist, in, out, duration, background/featured), rows with
  missing metadata marked with a warning icon and "missing artist"; actions
  Export CSV, Print.
- **Settings (Mod+,, WP27):** a dialog with a left list (Project, Audio,
  Appearance, Keys) and a form; every change is an undoable edit for project
  settings; Appearance holds theme, density, waveform scale and the gate and
  cut visibility defaults.
- **Record mode (WP12):** a full-window takeover on `--surface-app` in dark
  regardless of theme: big elapsed time, per-input meters, "Hold to stop · 2 s"
  with a fill that runs for 2 s, the log list; every other key is ignored and
  says so in the hint line. Placeholder only; designed in detail with WP12.
- **Keyboard sheet (?):** a dialog listing every command with its keys,
  grouped as the palette, searchable.

## 4. Visual language

### 4.1 Tokens: three layers

1. **Primitives** `--p-<family>-<lightness>`: raw colours, named by OKLCH
   lightness 0–100 (`-aNN` = alpha). Theme-independent. Only the theme blocks
   may use them.
2. **Semantic roles**: what a colour means (`--surface-lane`, `--text-secondary`,
   `--signal-candidate`, `--track-2-wave`, `--bus-1-spine` …). Each theme sets
   every one of them, only as `var(--p-…)` (or a number). The list is
   `grammar.js SEMANTIC_TOKENS`.
3. **Component tokens**: `--button-bg`, `--lane-bg`, `--kbd-text` …, only as
   `var(--semantic)`.

`style.css` uses layers 2 and 3. Canvases read layer 2 through
`grammar.js resolvePalette`, once per theme change. Enforced by
`ui/tests/tokens.test.js`: layering, completeness per theme, no colour
literal in any `ui/` file except `tokens.css`, and WCAG AA for every pair below.

### 4.2 Colour roles

Light is the default `:root`; dark applies by `prefers-color-scheme` unless
`data-theme="light"`, or by `data-theme="dark"`. The accent is a clear teal
(kuulas means "clear"); the playhead is a warm red that no track hue uses.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--surface-app` | `#e8ecee` | `#0f1214` | behind everything; the 1 px gaps between docks |
| `--surface-lane` | `#f6f8f9` | `#13171a` | timeline background |
| `--surface-lane-current` | `#e9f3f1` | `#172225` | the current track's lane and header (↑/↓ cursor) |
| `--surface-panel` | `#ffffff` | `#171b1e` | headers, panels, top and status bars |
| `--surface-raised` | `#ffffff` | `#1e2327` | popovers, palette, toasts (with --shadow-raised) |
| `--surface-sunken` | `#eef1f3` | `#101316` | inputs, wells, key chips |
| `--surface-hover` | `#eef2f4` | `#212729` |  |
| `--surface-active` | `#e2e8eb` | `#283034` | pressed controls, count pills |
| `--surface-scrim` | `rgb(16 24 28 / 0.32)` | `rgb(0 0 0 / 0.5)` | behind modal dialogs |
| `--border-subtle` | `#e3e8eb` | `#22282c` | lane separators, list dividers |
| `--border` | `#d3dadd` | `#2d3539` | panel edges, controls at rest |
| `--border-strong` | `#858f96` | `#66727a` | input outlines: >= 3:1 on panels |
| `--text` | `#13191c` | `#e7ecee` |  |
| `--text-secondary` | `#48545a` | `#aab4b9` |  |
| `--text-tertiary` | `#5c6870` | `#8f9aa0` | still >= 4.5:1: body text, never decoration |
| `--text-disabled` | `#9aa5ab` | `#566066` | disabled only (exempt from contrast) |
| `--text-on-accent` | `#ffffff` | `#04211d` |  |
| `--accent` | `#0a7a6b` | `#3dc9b3` | primary buttons, focus, range edges, the overview box |
| `--accent-hover` | `#086a5d` | `#5ad6c2` |  |
| `--accent-text` | `#0a6e60` | `#5ad6c2` | accent-coloured text on panels |
| `--accent-subtle` | `#dff1ed` | `#133a35` | selected rows, selected words |
| `--focus-ring` | `#0a7a6b` | `#5ad6c2` |  |
| `--warn` | `#b97a00` | `#f0b54a` | fills and strokes: solo, speed chip |
| `--warn-text` | `#8a5300` | `#f3c165` |  |
| `--warn-subtle` | `#fff1d6` | `#3a2c12` |  |
| `--danger` | `#c8321f` | `#ff776b` |  |
| `--danger-text` | `#b42d1c` | `#ff8a7f` |  |
| `--danger-subtle` | `#fde8e4` | `#3d1d1b` |  |
| `--ok` | `#1e8a4c` | `#6fd39a` |  |
| `--ok-text` | `#18794a` | `#7fdca6` |  |
| `--shadow-raised` | `0 6px 20px var(--p-gray-22-a14), 0 0 0 1px var(--p-gray-22-a8)` | `0 8px 24px var(--p-black-a45), 0 0 0 1px var(--p-gray-32)` |  |
| `--shadow-dialog` | `0 18px 48px var(--p-gray-22-a22), 0 0 0 1px var(--p-gray-22-a8)` | `0 20px 56px var(--p-black-a60), 0 0 0 1px var(--p-gray-32)` |  |
| `--playhead` | `#d93a26` | `#ff6b57` |  |
| `--play-start` | `#5c6870` | `#8f9aa0` | where the last play started (hollow mark) |
| `--selection-range` | `rgb(10 122 107 / 0.14)` | `rgb(61 201 179 / 0.16)` | in/out band on the scoped lanes |
| `--gain-line` | `#13191c` | `#e7ecee` |  |
| `--automation-line` | `#48545a` | `#aab4b9` |  |
| `--ruler-text` | `#48545a` | `#aab4b9` |  |
| `--ruler-tick` | `#a9b4ba` | `#4a555b` |  |
| `--signal-selected` | `#10161a` | `#ffffff` | 2 px outline: neutral, works on every hue |
| `--signal-partner` | `#48545a` | `#aab4b9` | dashed: what a move takes along |
| `--signal-muted-hatch` | `rgb(19 25 28 / 0.28)` | `rgb(231 236 238 / 0.22)` |  |
| `--signal-muted-opacity` | `0.35` | `0.35` |  |
| `--signal-unheard-opacity` | `0.45` | `0.45` |  |
| `--signal-unused-opacity` | `0.5` | `0.5` |  |
| `--signal-placeholder` | `#48545a` | `#aab4b9` | dashed outline of narration placeholders |
| `--signal-provisional` | `#5c6870` | `#8f9aa0` |  |
| `--signal-candidate` | `#c8321f` | `#ff776b` | stripes and edges of cut candidates |
| `--signal-candidate-fill` | `rgb(200 50 31 / 0.12)` | `rgb(255 119 107 / 0.13)` |  |
| `--signal-soft-cut` | `#c8321f` | `#ff776b` | a cut that kept its gap: edges and hatch |
| `--signal-soft-cut-fill` | `rgb(200 50 31 / 0.08)` | `rgb(255 119 107 / 0.09)` |  |
| `--signal-gate` | `#f6f8f9` | `#13171a` | the veil over a closed gate (lane colour) |
| `--signal-gate-opacity` | `0.7` | `0.7` |  |
| `--signal-damaged` | `#c8321f` | `#ff776b` |  |
| `--signal-damaged-fill` | `#fde8e4` | `#3d1d1b` |  |
| `--signal-removed` | `#c8321f` | `#ff776b` |  |
| `--signal-removed-fill` | `rgb(200 50 31 / 0.12)` | `rgb(255 119 107 / 0.13)` |  |
| `--signal-added` | `#1e8a4c` | `#6fd39a` |  |
| `--signal-drift` | `#c8321f` | `#ff776b` | solid badge with the offset |
| `--signal-drift-text` | `#ffffff` | `#1a0c0b` |  |
| `--signal-clipping` | `#c8321f` | `#ff776b` | the cap on a clipped column |
| `--signal-file-mark` | `#ffffff` | `#0f1214` | file mark chip background |
| `--signal-file-mark-text` | `#13191c` | `#e7ecee` |  |
| `--signal-free` | `#48545a` | `#aab4b9` |  |
| `--signal-seam` | `#48545a` | `#aab4b9` | hairline (split) and notch (jump cut) |
| `--signal-takes` | `#48545a` | `#aab4b9` |  |
| `--signal-note` | `#b97a00` | `#f0b54a` |  |
| `--signal-sync` | `#48545a` | `#aab4b9` |  |
| `--signal-tether` | `#48545a` | `#aab4b9` |  |
| `--role-speech` | `#48545a` | `#aab4b9` | strip pattern: solid |
| `--role-speech-mix` | `#48545a` | `#aab4b9` | strip pattern: dashed |
| `--role-music` | `#7a715e` | `#8e8572` | strip pattern: dotted |

Contrast, checked by the test (WCAG 2.2: text ≥ 4.5, graphics and outlines ≥ 3):

| Text token | on panel (light / dark) | on lane | on raised |
|---|---|---|---|
| `--text` | 17.7 / 14.5 | 16.7 / 15.1 | 17.7 / 13.3 |
| `--text-secondary` | 7.8 / 8.2 | 7.3 / 8.5 | 7.8 / 7.5 |
| `--text-tertiary` | 5.7 / 6.0 | 5.4 / 6.3 | 5.7 / 5.5 |
| `--accent-text` | 6.2 / 9.8 | 5.8 / 10.2 | 6.2 / 8.9 |
| `--warn-text` | 6.3 / 10.4 | 5.9 / 10.8 | 6.3 / 9.5 |
| `--danger-text` | 6.3 / 7.6 | 5.9 / 7.9 | 6.3 / 6.9 |
| `--ok-text` | 5.4 / 10.5 | 5.1 / 10.9 | 5.4 / 9.6 |
| `--text-on-accent` on `--accent` | 5.2 / 8.2 | | |
| `--focus-ring` on `--surface-panel` | 5.2 / 9.8 | | |
| `--border-strong` on `--surface-panel` | 3.3 / 3.5 | | |
| `--playhead` on `--surface-lane` | 4.3 / 6.4 | | |
| `--signal-selected` on `--track-0-body` | 16.5 / 15.7 | | |
| `--signal-drift-text` on `--signal-drift` | 5.3 / 7.4 | | |

### 4.3 Track hues (speaker identity)

Six speaker hues and one role colour for music. A hue belongs to the
**speaker**, not the track: tracks with the same `speaker` share it
(`trackHues`); music takes the music role colour and does not use up a hue.
Each hue has five parts: `wave` (bars), `body` (clip fill), `body-alt` (the
other file's tone, zebra), `edge` (outline, header pill), `label` (clip name).

| Hue | Part | Light | Dark | Checked (light / dark) |
|---|---|---|---|---|
| 0 | wave | `#1157a4` | `#5e9ae7` | wave/body 6.5 / 5.4; wave/alt 5.6 / 4.4 |
| 0 | body | `#ecf4ff` | `#192431` |  |
| 0 | body-alt | `#d4e5fb` | `#243346` |  |
| 0 | edge | `#1b589e` | `#689bdb` | edge/lane 6.7 / 6.3 |
| 0 | label | `#164781` | `#b9daff` | label/body 8.4 / 10.9 |
| 1 | wave | `#b07100` | `#fac463` | wave/body 3.6 / 9.9; wave/alt 3.2 / 8.1 |
| 1 | body | `#fbf2e6` | `#2a2112` |  |
| 1 | body-alt | `#f3e2cb` | `#3c2f19` |  |
| 1 | edge | `#a06700` | `#cfa354` | edge/lane 4.4 / 7.7 |
| 1 | label | `#693c00` | `#f0d3a3` | label/body 8.4 / 11.0 |
| 2 | wave | `#ad456b` | `#df7a9b` | wave/body 4.9 / 5.6; wave/alt 4.2 / 4.6 |
| 2 | body | `#ffeff3` | `#2f1d22` |  |
| 2 | body-alt | `#f8dae2` | `#432931` |  |
| 2 | edge | `#a9496b` | `#d6809c` | edge/lane 5.1 / 6.4 |
| 2 | label | `#742945` | `#ffc5d5` | label/body 8.8 / 10.8 |
| 3 | wave | `#008bb3` | `#61e3ff` | wave/body 3.6 / 10.4; wave/alt 3.1 / 8.5 |
| 3 | body | `#e7f7fc` | `#12262e` |  |
| 3 | body-alt | `#ccebf5` | `#193641` |  |
| 3 | edge | `#0084a9` | `#50b9df` | edge/lane 4.0 / 8.0 |
| 3 | label | `#005370` | `#a6e2fb` | label/body 7.7 / 11.1 |
| 4 | wave | `#643185` | `#a57fd0` | wave/body 8.1 / 5.0; wave/alt 7.0 / 4.1 |
| 4 | body | `#f7f0fd` | `#271f2e` |  |
| 4 | body-alt | `#eaddf5` | `#382c41` |  |
| 4 | edge | `#633481` | `#9c78c4` | edge/lane 8.4 / 5.1 |
| 4 | label | `#5a3473` | `#e6cbfb` | label/body 8.7 / 10.8 |
| 5 | wave | `#4e8626` | `#96c166` | wave/body 4.0 / 7.5; wave/alt 3.5 / 6.1 |
| 5 | body | `#eef6ea` | `#1e2616` |  |
| 5 | body-alt | `#d9e9d1` | `#2b3620` |  |
| 5 | edge | `#51852f` | `#94b96d` | edge/lane 4.2 / 8.1 |
| 5 | label | `#2b5409` | `#c8e1b1` | label/body 8.0 / 11.1 |
| music | wave | `#8a7f69` | `#b5aa92` | wave/body 3.5 / 7.0; wave/alt 3.0 / 5.7 |
| music | body | `#f2f0ec` | `#24211c` |  |
| music | body-alt | `#e4e1da` | `#33302a` |  |
| music | edge | `#7a715e` | `#8e8572` | edge/lane 4.5 / 4.9 |
| music | label | `#4f4735` | `#d8d0bf` | label/body 8.1 / 10.5 |

CVD separation, light, min OKLab ΔE×100 between waveform colours (first four / all six): normal 14.9 / 13.5, deuteranopia 11.0 / 5.4, protanopia 10.5 / 1.8, tritanopia 7.8 / 7.1.

CVD separation, dark, min OKLab ΔE×100 between waveform colours (first four / all six): normal 19.6 / 10.8, deuteranopia 14.9 / 3.6, protanopia 11.3 / 5.1, tritanopia 15.1 / 11.8.

The order (blue, amber, rose, sky, violet, green) was searched so the first
four, the common case, stay apart under deuteranopia, protanopia and
tritanopia (values above). Hues 5 and 6 are close under protanopia in light;
they lean on the twins (track name, pill position, file name), which is why no
hue is ever the only cue.

### 4.4 Bus colours (group identity)

Four muted hues, deliberately lower in chroma than the speaker hues so a spine
never reads as a speaker. They cycle with A, B, C, D …; the letter is the twin.

| Bus | Letter | Spine light / dark | Text light / dark | Checked text/panel, spine/panel (light; dark) |
|---|---|---|---|---|
| 1 | A | `#5970a4` / `#8ba4db` | `#374c79` / `#bed1f9` | 8.5, 4.9; 11.3, 7.0 |
| 2 | B | `#797435` / `#aca868` | `#544f11` / `#d6d4a7` | 8.4, 4.8; 11.4, 7.1 |
| 3 | C | `#8e5f89` / `#c391be` | `#653c62` / `#e8c3e4` | 8.8, 5.1; 11.0, 6.7 |
| 4 | D | `#9b6147` / `#d29478` | `#713e26` / `#f4c5b1` | 8.7, 5.0; 11.1, 6.8 |

The band is the spine colour at 7 % (light) / 9 % (dark) alpha behind the
group, doubled on the header row.

### 4.5 Type

- `--font-ui`: the system stack (SF Pro on Mac, Segoe UI Variable on Windows,
  Ubuntu/Cantarell/Noto on Linux). Native, no download, full Finnish.
- `--font-mono`: ui-monospace/SF Mono/Cascadia Mono, used only for ruler
  labels and file marks (fixed-width digits in a canvas, where
  `font-variant-numeric` is not available).
- Times everywhere else: `--font-ui` with `font-variant-numeric: tabular-nums`.
- Scale: 11 (`--text-xs`: badges, ruler, key chips) · 12 (`--text-sm`:
  controls, panel headings, meta) · 13 (`--text-md`: body) · 15 (`--text-lg`:
  transcript, dialog titles, inspector title) · 20 (`--text-xl`: timecode).
  Weights 400, 500, 600 only. Headings are sentence case, never uppercase
  (calmer, and long Finnish words stay readable).

### 4.6 Spacing, radii, elevation, density

- Spacing on a 4 px grid: 2, 4, 6, 8, 12, 16, 24, 32 (`--space-1…8`).
- Radii: 2 (badges, key chips) · 4 (controls) · 6 (popovers, cards, toasts) ·
  10 (dialogs, palette) · pill (chips). **Clips are square**: crisp edges read
  as edit points.
- Elevation: flat docks; `--shadow-raised` for popovers and toasts;
  `--shadow-dialog` for dialogs over `--surface-scrim`. In dark, raised
  surfaces are also lighter (`--surface-raised`) because shadows barely show.
- Density: `comfortable` (default) and `compact` (`data-density="compact"`:
  12 px body, 22 px controls, 40 px lanes, 38 px top bar, narrower columns).
  Compact is for laptops and for editors who know the keys.

### 4.7 Motion

90 ms hover/press (`--dur-fast`), 140 ms chips and tabs (`--dur-base`),
120 ms lane height and focus-mode shrink (`--dur-layout`), 600 ms "this
changed" flash after undo (`--dur-flash`), all `--ease-standard`. Nothing
moves on its own except the playhead and progress. `prefers-reduced-motion`
sets the durations to 0; the undo flash becomes a static outline for 1.2 s.

### 4.8 Focus

`:focus-visible` gets a 2 px `--focus-ring` outline, 2 px offset (inset −2 px
on the timeline canvas). The focused panel (F6 cycle) shows a 2 px accent
line across its top edge; the panel heading turns `--text`. The focus ring is
never removed or replaced by colour alone.

## 5. The visual grammar

### 5.1 Channels

Each channel carries one meaning (tested). A clip can show many signals, but
each in its own channel, so they never fight.

| Channel | Meaning | Drawn as |
|---|---|---|
| hue | identity: who speaks / what source | clip body, wave and edge in the track hue |
| tone | identity: which file within a track | `body` vs `body-alt` (zebra) |
| opacity | audibility | the whole clip, or a band over part of it, fainter |
| weight | selection | 2 px neutral outline |
| dash | reality: not real audio yet | dashed outline |
| scope | edit scope | dashed 1 px ring inset 2 px |
| pattern | absent or may be absent | hatch or stripes |
| strip | role (speech, mix, music) | 2 px top strip with a dash pattern |
| badge | facts attached to the clip | small chips after the name |
| cap | level | 3 px block on a clipped column |
| seam | joins | hairline or notch where clips meet |
| bar | change since a checkpoint | 3 px side bars |
| spine, band | grouping (bus) | header spine; tinted band behind the group |
| line | attachment | tether from clip to anchor |
| notch | annotation | triangle in the top edge |

### 5.2 Every signal

Generated from `ui/grammar.js` (priority order; lower is more important;
"always" = never dropped). Light and dark values are the resolved tokens.
"Status": built in the editor today / shown in the prototype, built with its
WP / planned.

| # | Signal | Channel · meaning | Priority | Light | Dark | Non-colour twin | When shown | Keys | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **speaker** | hue · identity | 0 (always) | track/bus/label hues | track/bus/label hues | track name in the header and file name on the clip; the header swatch is a short pill | always | — | built |
| 2 | **file-zebra** | tone · identity | 0 (always) | track/bus/label hues | track/bus/label hues | file mark chip and file name on each clip; a seam marks every change of file | neighbouring clips on one track come from different files | — | built |
| 3 | **selected** | weight · selection | 0 (always) | `#10161a` | `#ffffff` | 2 px outline (shape), plus the inspector shows the clip | the clip is selected | click, Tab, Mod+A | built |
| 4 | **placeholder** | dash · reality | 0 (always) | `#48545a` | `#aab4b9` | dashed outline, no waveform, the script text in italics inside | narration placeholder (WP43) | T | prototype |
| 5 | **damaged** | pattern · absence | 0 (always) | `#c8321f` `#fde8e4` | `#ff776b` `#3d1d1b` | cross-hatch, a '!' badge with the word 'damaged', and the reason on hover | media that cannot be read there (plays silence) | — | prototype |
| 6 | **drift** | badge · facts | 0 (always) | `#c8321f` `#ffffff` | `#ff776b` `#1a0c0b` | solid badge with the offset in text ('−312 ms'), cause on hover | undecided drift from the sync group (WP19a) | R resyncs, U frees | prototype |
| 7 | **bus** | spine · grouping | 0 (always) | track/bus/label hues | track/bus/label hues | letter badge (A, B, C) in the bus header, the transcript and the inspector | a track is on a bus: the spine runs from the bus header through its tracks | — | built |
| 8 | **bus-band** | band · grouping | 0 (always) | — | — | drawn only together with the spine (the band is a tint of the spine's colour) | behind a bus's header and member lanes | — | built |
| 9 | **muted** | opacity · audibility | 1 (always) | `rgb(19 25 28 / 0.28)` `0.35` | `rgb(231 236 238 / 0.22)` `0.35` | diagonal hatch over the clip; M pressed in the header for a muted track | the clip is muted | N | built |
| 10 | **unheard** | opacity · audibility | 1 (always) | `0.45` | `0.45` | header says 'not heard: solo' in its tooltip and the M button turns dashed | another track is soloed, or this track is muted | Shift+S, Shift+M | prototype |
| 11 | **gate** | opacity · audibility | 1 (always) | `#f6f8f9` `0.7` | `#13171a` `0.7` | the waveform under the band is drawn flat (a 1 px floor line), with a small gate tick at each edge; hover says 'Mic closed' and offers 'Open this stretch' | Auto-Silence: one merged gate per track closes the mic (WP44); a per-lane toggle shows or hides it | Alt+Mod+P runs Auto-Silence | prototype |
| 12 | **candidate** | pattern · absence | 1 (always) | `#c8321f` `rgb(200 50 31 / 0.12)` | `#ff776b` `rgb(255 119 107 / 0.13)` | diagonal stripes across the group's lanes and a 'cut?' flag in the ruler | an open cut candidate (WP18) | D, ] [, Enter, Backspace | prototype |
| 13 | **soft-cut** | pattern · absence | 1 (always) | `#c8321f` `rgb(200 50 31 / 0.08)` | `#ff776b` `rgb(255 119 107 / 0.09)` | hatch plus a solid 2 px edge at each end in the cut colour, and the word 'cut' when wide enough; the context menu says 'Restore' | a stretch cut without closing the gap ('Cut, keep gap'); 'Show cuts' (on by default) hides or shows them | Backspace on a range; Restore from the menu or the palette | prototype |
| 14 | **removed** | pattern · absence | 1 (always) | `#c8321f` `rgb(200 50 31 / 0.12)` | `#ff776b` `rgb(255 119 107 / 0.13)` | a ghost outline with hatch and a '−' glyph | changes view (WP31): audio in A that is gone in B | Alt+Mod+D, ] [ | planned |
| 15 | **added** | bar · change | 1 (always) | `#1e8a4c` | `#6fd39a` | a 3 px bar on the clip's left and right edges and a '+' glyph | changes view (WP31): audio in B that was not in A | Alt+Mod+D, ] [ | planned |
| 16 | **provisional** | dash · reality | 2 (always) | `#5c6870` | `#8f9aa0` | short dashes (2 on, 2 off) on the outline | an edit is shown but the engine has not confirmed it after 150 ms | — | prototype |
| 17 | **partner** | scope · edit scope | 2 (always) | `#48545a` | `#aab4b9` | dashed 1 px outline inset 2 px, neutral | a clip is selected: its sync partners that a move takes along (WP19a) | E toggles group editing | prototype |
| 18 | **clipping** | cap · level | 2 | `#c8321f` | `#ff776b` | a 3 px block on top of the clipped column (shape) and a line in the inspector | a peak at or above −0.1 dBFS | — | built |
| 19 | **file-mark** | badge · facts | 3 | `#ffffff` `#13191c` | `#0f1214` `#e7ecee` | two characters from the content hash; the same on every track | a track holds clips from more than one file | — | built |
| 20 | **free** | badge · facts | 4 | `#48545a` | `#aab4b9` | outlined badge with an unlinked-chain glyph and '+300 ms · free' | a clip freed from its sync group on purpose (U) | U | prototype |
| 21 | **seam-jump** | seam · joins | 4 | `#48545a` | `#aab4b9` | a small V notch top and bottom at the join (shape) | two clips of one file meet but audio between them was removed; hover offers 'Put back' (a ripple cut) | Tab stops here | built |
| 22 | **takes** | badge · facts | 5 | `#48545a` | `#aab4b9` | stacked top-right corner (two offset edges) and '2/3' | a take set (WP19e) | Alt+] / Alt+[ | prototype |
| 23 | **note** | notch · annotation | 5 | `#b97a00` | `#f0b54a` | a triangular notch in the top edge; the text on hover | a note or marker on the clip's audio | M | prototype |
| 24 | **unused** | opacity · audibility | 6 | `0.5` | `0.5` | the clip bin lists it under 'not in the programme' | clip bin and cards: material not used in the open edit | — | planned |
| 25 | **sync** | badge · facts | 6 | `#48545a` | `#aab4b9` | chain glyph and the group number ('⛓ 1') | on the selected clip and its partners only; never on every clip | Y marks in sync | prototype |
| 26 | **tether** | line · attachment | 6 | `#48545a` | `#aab4b9` | a thin line from the clip's start down to its anchor, ending in a dot | a connected clip (WP19b) | Alt+Mod+C | planned |
| 27 | **label** | badge · facts | 7 | track/bus/label hues | track/bus/label hues | a square flag in the top-right corner; its name on hover and in the inspector | the user gave the clip a label colour (never set automatically) | — | planned |
| 28 | **seam-split** | seam · joins | 8 | `#48545a` | `#aab4b9` | a 1 px hairline (shape) | two clips of one file meet with nothing removed between them | — | built |
| 29 | **role** | strip · role | 9 | `#48545a` `#48545a` `#7a715e` | `#aab4b9` `#aab4b9` `#8e8572` | strip pattern: solid speech, dashed speech mix, dotted music; role icon in the header | off on the timeline (the header says it); on in the clip bin and cards | — | prototype |

**At most three ranked signals per clip.** `pickSignals(active)` keeps every
"always" signal, then the three highest-priority others; the rest collapse
into a "+N" badge listing them on hover. The gallery screen shows it.

### 5.3 Several recordings on one track (owner, 17.10.2026)

Hue already means the speaker, so the file is never a hue:

- **Zebra tone:** the body alternates between `body` and `body-alt` whenever a
  clip comes from a different file than the clip before it (`zebraSteps`).
  Clips of one file in a row keep their tone.
- **File mark:** a 2-character chip before the file name, derived from the
  SHA-256 (`fileMark`, alphabet without 0/O, 1/I, 2/Z, 5/S, 8/B). The same
  recording has the same mark on every track. Shown only on tracks that hold
  more than one file (`needsFileMark`), so the common single-file track stays
  clean. The inspector shows it too.
- **Sync mark** is separate: chain glyph + group number ("⛓ 1"), because "same
  file" and "recorded together" are different relations.
- **Seams** (`seamKind`): a 1 px hairline where two clips of one file meet with
  nothing removed (a plain split); a V notch top and bottom where audio between
  them was removed (a jump cut: where the auto crossfade goes, and where hover
  offers "Put back"); nothing extra at a change of file (tone and outlines
  show it).
- **Manual label colour** (planned): a user-chosen colour as a square flag in
  the top-right corner (`--label-1…6`), never set automatically and never
  used for anything else.

### 5.4 Mute, gate and soft cut (owner, 17.10.2026; WP44)

Three ways audio is not heard, three different looks:

| | Mute | Gate (Auto-Silence) | Soft cut |
|---|---|---|---|
| What it is | the user muted a clip | one merged gate per track closes the mic | a stretch cut without closing the gap |
| Look | clip at `--signal-muted-opacity` + neutral diagonal hatch | a dim band (`--signal-gate` at `--signal-gate-opacity`) over the lane, waveform drawn flat under it, no hatch, a small tick at each edge | hatch in the cut colour, `--signal-soft-cut-fill`, solid 2 px cut-colour edges, "cut" when wide |
| Wording | "Mute clip" / "Unmute" (N) | hover "Mic closed" · click "Open this stretch" | "Cut, keep gap" · "Restore" (ripple cuts: "Put back" on the notch) |
| Visibility | always | per-lane show/hide toggle (lane context menu and palette) | "Show cuts" toggle, on by default |

### 5.5 What to leave out (recommendations)

- **Role strip on the timeline:** off. The header icon already says it on every
  lane; repeating it on every clip is noise. On in the clip bin and on cards,
  where clips from different roles sit together.
- **Sync badge on every clip:** no. Only on the selection and its partners,
  and always for drift. A timeline full of "⛓ 1" says nothing.
- **Gain line at 0 dB:** hidden unless the clip is selected.
- **Clipping cap at wide zoom** (whole edit): kept, but merged per pixel
  column; a clip that clips gets a "clipping" line in the inspector rather
  than a badge.
- **Provisional dashes:** only after 150 ms without confirmation (normally
  never seen; 14 ms median round trip measured).
- **File mark:** only on tracks with two or more files.

## 6. Buses

- **Position:** a bus is a group header *above* its member tracks, like a
  folder (`lanes.js layoutRows`): it appears where its first member would be,
  its members gather under it in track order, tracks on no bus keep their
  place between groups, and buses with no members go last. (The model's track
  order is unchanged; see open question 7.)
- **Identity:** the spine (4 px, bus colour, header through every member), the
  band (faint tint behind header and member lanes, doubled on the header row),
  and the letter badge (A, B, …, the twin) in the header, the track's bus
  picker, the transcript speaker gutter, the inspector's bus line, and every
  mixer-like place (export stems list, music report, settings). Speaker hue
  stays on clips and the track pill; bus colour stays in spine, band and badge.
- **Expanded:** header row 44 px (name, M, S; gain, pan), members below.
- **Collapsed** (chevron, or Alt+← on a member): one row at lane height
  showing the members' summed half waveform in the bus spine colour and the
  member count; members hidden. Selection and edits on a collapsed bus apply
  to all its members (time-shifting edits keep the sync rule).
- **Empty bus:** the header alone, name in italics, tertiary; sits last.
- **No bus:** no spine, no band; the track goes straight to the master.
- **Assigning:** the track's bus picker (letter + chevron; the menu lists
  "A · Voices", "B · Music", "– · No bus"), or drag a track header onto a
  group: a 2 px insertion line in the bus colour shows where it lands; dropping
  on a header appends it. Both are one undoable edit.
- **Bus mute/solo/gain:** M mutes the bus send (a muted bus stays silent under
  solo, WP24.1); **S solos every member as a set** (exclusive, like track solo;
  open question 6); gain and pan as on tracks, coalesced drags.

## 7. Waveforms and the timeline

### 7.1 Drawing a clip

- Body: `body` (or `body-alt`), inset 2 px top and bottom, square, 1 px `edge`
  outline. Bars: `wave`, opaque (contrast with the body is checked).
- **Half waveform** (default, Hindenburg): each pixel column draws
  `max(|min|, |max|)` as a bar rising from the clip's bottom edge, so the top of
  the clip stays free for the name, badges and the gain line. **Full**
  (classic) waveform: min/max around the centre; View menu or Alt+Mod+W.
- Scale: linear by default; dB-shaped (−48 dBFS at the floor) as an option,
  recommended as the speech default (open question 1).
- Waveform height factor (Alt+wheel, Alt+= / Alt+-): display only, shown as an
  amber "×4" chip in the top bar while not 1:1; click resets.
- Bars never exceed 160 px; in a taller lane (focus mode) the space above holds
  the automation band.
- Name: 11/600 in `label` on a backing of the body colour at 85 % (bars never
  cross the text), clipped to the clip; hidden below 40 px lanes or 30 px
  clip width. The file mark precedes it where needed; badges follow.
- Fades: the curve in `edge`, the region above it veiled with the lane colour at
  55 %, a 6 px square handle at the fade end. Crossfades at ripple joins: a
  pair of triangles in `edge` at 30 %.
- Gain line (clip gain): dashed `--gain-line` at 75 %, at the clip's gain on a
  +12 … −30 dB scale; envelope points as 3 px dots joined by lines.
- Track automation (ducking): a 1.5 px `--automation-line` in the lower third,
  with its value on a lane-coloured backing ("ducking −12 dB").
- Clipping: a 3 px `--signal-clipping` block on top of each column whose peak
  is ≥ −0.1 dBFS.

### 7.2 Zoom levels: what is drawn

| Level (status bar) | Frames per pixel at 1000 px | Drawn |
|---|---|---|
| samples | < 1 | (planned: needs sample tiles) the sample line with a dot per sample at ≥ 8 px per sample |
| 100 ms – 2 s | 5 – 96 | bars from the 256-frame tiles, one per column; seams and notches exact; fade curves smooth |
| 5 s – 1 min | 240 – 2 880 | bars; envelope points; candidate flags labelled |
| 2 – 10 min | 5 760 – 28 800 | bars; labels only on clips ≥ 30 px; badges collapse to the most important one |
| 30 min – whole edit | ≥ 86 400 | bars from the coarsest tiles; clip names only where they fit; candidates as flags without text; clipping caps merged per column |

Waveforms come from peak tiles in a worker (`waveform.worker.js`); the overlay
(names, lines, selection, playhead) is redrawn on its own each frame.

### 7.3 Playhead, selection, snapping

- **One playhead** (Hindenburg model): it is both the edit point and the play
  position. Stop leaves it where playback stopped; the start of the last play
  is marked in the ruler (hollow triangle) so Shift+Space-style "play from
  where I started" has a visible target. While playing it is 1 px; a stopped
  playhead is the same (no blinking).
- **Clip selection:** 2 px `--signal-selected` (neutral: max contrast on every
  hue). Its sync partners get the dashed scope ring, so you see what a move
  takes along before you press a key (WP19a).
- **Range (in/out):** `--selection-range` fill **on exactly the lanes the next
  time-shifting edit will touch** (the group's lanes, not unrelated music),
  accent 1 px edges and inward flags in the ruler. Words selected in the
  transcript show the same range.
- **Snap feedback** (WP6): when a drag snaps (clip edges, playhead, markers,
  8 px), a 1 px accent guide line spans the lanes for as long as the snap holds,
  and the timecode tooltip at the pointer shows the snapped time. Holding Mod
  disables snapping; the guide disappears.
- **Undo flash:** after undo/redo the changed clips get a 2 px accent outline
  that fades over 600 ms (static 1.2 s with reduced motion), and the view
  scrolls to them if they are off-screen.

## 8. Interaction model

### 8.1 Focus between panels

Timeline is home; Esc always returns there. F6 / Shift+F6 cycle timeline →
transcript → sidebar (the current tab) → timeline. A click focuses its panel.
The focused panel shows the 2 px accent top line; the status bar hints follow
it. Inside the timeline, Tab is an edit key (next edit point); inside panels
Tab moves between controls as usual. No keyboard trap: Esc and F6 always leave.
Dialogs and the palette trap focus while open and give it back on close.

### 8.2 Modes and their indicators

| Mode | Where it shows | Look |
|---|---|---|
| Group editing off | top bar chip | amber, "Group editing off E" |
| Speed ≠ 1× | top bar chip | amber "1.5× ." |
| Solo active | top bar chip + S buttons | amber |
| A/B comparison | top bar chip | neutral, "A · B −2.3 dB matched", the side playing in 600 |
| Focus mode | top bar chip + strips | neutral "Focus: Ville · Esc" |
| Close / wide view | status bar | the toggle's text |
| Follow paused | status bar | follow button text turns amber |
| Tab mode | status bar | "Tab: clip edges / transients / words" |
| Waveform height ≠ 1 | top bar chip | amber "×4" |
| Disconnected | top bar chip + status bar | danger chip; "Saved up to … · edits paused" |

### 8.3 Pointer and trackpad

Click selects (Shift adds, Mod toggles); click on empty lane sets the playhead
and clears the selection; click in the ruler seeks; drag in the ruler scrubs
(WP26). Drag affordances: the pointer is `grab` over a clip body,
`ew-resize` within 4 px of an edge (trim), `ns-resize` on the gain line,
`crosshair` with Alt over the gain line (add point); a dragged clip leaves a
dashed ghost of where it was. Trackpad scrolls naturally both ways; pinch and
Mod+wheel zoom, settling on a level within 8 %; Alt+wheel changes waveform
height; Shift+wheel always scrolls time.

### 8.4 Control states

| State | Buttons | Chips / toggles | Inputs | Canvas items |
|---|---|---|---|---|
| rest | `--button-bg`, 1 px `--button-border` | 1 px `--border`, text secondary | `--input-bg`, 1 px `--input-border` | as drawn |
| hover | `--button-hover-bg`, border `--button-hover-border` | border strong | border tertiary | pointer cursor changes; clip edge highlight 1 px |
| pressed (active) | `--button-active-bg` | — | — | — |
| on (aria-pressed) | surface-active bg + strong border; M neutral fill; S amber fill | warn/danger/info variants | — | — |
| focus | 2 px focus ring | same | same | timeline: inset ring |
| disabled | text `--text-disabled`, no hover | hidden instead where possible | 50 % opacity of the label | — |
| invalid | — | — | 1 px danger border + ring, message below | — |

### 8.5 Long jobs, errors, undo

- Jobs: the top bar chip and its popover; per-media progress also as a 2 px
  bar under the track name in its header (planned). Never modal; cancellable.
- Edits: provisional at once; after 150 ms unconfirmed the clip outline turns
  to short dashes; on refusal the screen reverts and a toast says why.
- Undo: Mod+Z / Shift+Mod+Z along the current branch; toast "Undid: cut at
  12:31 · Redo"; crossing a session marker says so; changed clips flash.
- Errors: where they happened first (field, clip badge, job row), a toast
  with the fix second. A bad file costs that file: "Imported 3 files. Could
  not import haastattelu-3.m4a: …".
- Confirmation dialogs only for what undo cannot bring back (section 1.6).

## 9. Keys: what the UI reserves and how it shows them (for WP5)

This section does not define the keymap (WP5 does, from Hindenburg's list); it
fixes how keys are shown and which keys the UI itself needs.

**Reserved by the UI shell:** Space (transport, everywhere except text fields),
Esc (back to the timeline; closes popovers, palette, focus mode), F6 /
Shift+F6 (panels), Mod+K (palette), ? (keyboard sheet), Tab/Shift+Tab (edit
points inside the timeline only), Enter and Backspace (act on the focused
panel's current item: the status bar always says what they will do there),
Alt+← / Alt+→ (collapse / expand the current bus; proposed), ↑/↓ (current
track).

**Showing keys:** key chips (`kbd`) in the key's platform form: `⌘⇧⌥⌃` on Mac
in Apple's order, "Ctrl+Shift+Alt+" elsewhere, named keys translated
(`i18n.js formatShortcut`: "Välilyönti" for Space in Finnish). Where: inside
the Play button, in tooltips ("Split · B"), on palette rows, in the inspector
next to fields, in the status bar hints for the focused panel, on toast
actions ("Undo ⌘Z"). Never in body text.

**Conflicts found** (resolve in WP5; recommendations in brackets):

1. `=` is zoom in (WP4) and opens Spot (WP19f). [Spot = Mod+J "Jump to time".]
2. `+`/`-` change clip gain when clips are selected but zoom otherwise (WP5
   change list). A modal meaning on the most-pressed keys. [Keep zoom on = / -
   always; clip gain stays Shift+Mod+↑/↓.]
3. Mod+H (zoom to selection) hides the app on macOS. [Drop it; Shift+Z already
   fits the selection.]
4. In a browser tab Chrome keeps Cmd/Ctrl+T, +W, +N, +Q and Shift+Mod+T
   (reopen tab): Mod+T import and Shift+Mod+T transcribe cannot work until the
   desktop wrapper (WP15). [Mod+I import and Shift+Mod+I transcribe as aliases
   now.] Mod+L (automix) focuses the address bar in Chrome: verify it can be
   intercepted.
5. Mod+F is fade (WP5) but every user expects find. [Mod+F = find in the
   transcript / palette; fade stays G.]
6. On the Finnish keyboard `[` and `]` need Option/AltGr (Option+8/9 on a Mac)
   and `` ` `` is a dead key: the candidate keys (] / [), take keys (Alt+] /
   Alt+[) and A/B (`) cannot be typed as written. [Bind them by physical key
   (`event.code` BracketLeft/BracketRight = the Å and ¨ keys, Backquote = §),
   as keys.js already does for Z.]
7. Backspace means delete clips (gap), reject candidate (WP18), cut words
   (transcript) and now "Cut, keep gap" (WP44); Shift+Space means play
   selection and preview candidate. [Acceptable only because they are scoped
   by focus and the current item; the status bar must say which one applies.]
8. F6 in Chrome also cycles the browser's own toolbar focus. [Verify in WP5;
   if the page cannot keep it, add Ctrl+` as the panel key in the browser.]

## 10. Themes

### 10.1 Themes are data

A theme is a set of overrides of the **semantic** tokens (layer 2). The shipped
light and dark themes are the two blocks in `tokens.css`. The choice is a
per-viewer setting: System (follow the OS), Light, Dark; today stored in
`localStorage` (`kuulas.theme`), to move to remembered settings (WP35). A theme
change re-resolves the canvas palette once (`timeline.refreshTheme`,
`overview.refreshTheme`) and repaints everything; the OS switching light/dark
does the same.

### 10.2 User theme manifest (format)

```json
{
  "name": "Late night",
  "base": "dark",
  "density": "compact",
  "tokens": {
    "--accent": "#ffaa00",
    "--surface-lane": "#0b0d0e",
    "--signal-muted-opacity": "0.3"
  }
}
```

- `base`: `light` or `dark`; every token not listed comes from it.
- `tokens`: only names from `SEMANTIC_TOKENS` (not primitives, not component
  tokens, not shadows); values `#rrggbb`, `rgb(r g b / a)`, or 0–1 for
  `*-opacity` tokens.
- `grammar.js themeFromManifest(manifest)` validates it and returns
  `{errors, attribute, base, density, css}`; a theme with any error is not
  applied. It is applied as `<html data-theme="dark" data-user-theme="late-night">`
  with the returned CSS in a `<style>` element. Loading manifests from the user
  config folder and a contrast check before applying (reuse the test's pairs)
  are planned with WP35.

### 10.3 Planned variants

- **High contrast:** text and borders to 7:1, `--border` = `--border-strong`,
  outlines 2 px, hatch alpha doubled, bands off; selection 3 px.
- **Colour-blind safe (deutan/protan):** speaker hues replaced by a set ordered
  for the specific type (blue, orange, sky, yellow, magenta, grey), seams and
  file marks always on, the bus band replaced by a dotted spine pattern per bus.
- Both as manifests over light and dark, checked by the same contrast test.

## 11. Component inventory

| Component | File(s) | States | Main tokens | Acceptance checks |
|---|---|---|---|---|
| Design tokens | `ui/tokens.css` | light, dark (OS / chosen), comfortable, compact, reduced motion | all | `tokens.test.js` green; prototype synced |
| Grammar registry | `ui/grammar.js` | — | names every semantic token | `grammar.test.js`, `tokens.test.js` green |
| Canvas palette | `ui/theme.js` | per theme change | via `resolvePalette` | `theme.test.js`; theme button repaints canvases |
| Window grid | `ui/index.html`, `ui/style.css` (`.editor`) | sizes per density | `--frame-gap`, sizes | no page scroll at 960×600; Finnish labels fit |
| Top bar | `index.html` `.toolbar`, `app.js` | empty, normal, playing, disconnected | `--button-primary-*`, chips | Play shows its key; chips only when not default |
| Timecode | `.timecode` | — | `--text-xl` | tabular; Finnish comma |
| Mode chips | `.chip.warn/.danger/.info` | hidden / shown | `--warn-*`, `--danger-*` | text, not only colour |
| Jobs chip + popover | (planned) `jobs.js` | none, running, failed | `--accent`, `--danger-text` | cancel works by keyboard |
| Track header | `ui/tracks.js`, `.track-header` | normal, current, compact, strip, muted, soloed, unheard, renaming | `--track-colour`, `--bus-*`, `--header-bg-current`, `--mute-on-bg`, `--solo-on-bg` | name ellipsis + tooltip; role icon has accessible name |
| Bus header | `ui/tracks.js`, `.bus-header` | expanded, collapsed (planned in app), no members | `--bus-spine/band/text` | letter badge visible; order follows `layoutRows` |
| Bus picker | `.bus-select` (app: a native select whose option text starts with the letter, so the narrow box shows it; replace with the prototype's letter button + menu, `.bus-pick`, when menus exist) | none, bus | `--border`, `--bus-text` | shows the letter; accessible name "Track bus" |
| Lane layout | `ui/lanes.js` | — | `--lane-h`, `--bus-h` | `lanes.test.js` |
| Waveform layer | `ui/paint.js`, `waveform*.js` | loading tiles, drawn, current lane, bus band, zebra, clipping | track parts, `--signal-clipping`, bands | `paint.test.js`, `waveform.test.js`; < 8 ms per frame |
| Timeline overlay | `ui/timeline.js` | names, file marks, seams, gain, automation, range, playhead | marks, signals | names never crossed by bars; seams per `seamKind` |
| Ruler | `ui/ruler.js`, `timeline.js` | ticks, flags | `--ruler-*` | labels ≥ 80 px apart; flags hide labels |
| Overview | `ui/overview.js` | empty, normal | wave colours, `--accent`, `--selection-range` | click/drag scrolls |
| Transcript | (WP7) `transcript.js` | empty, transcribing, normal, word selected, focus-dimmed | `--accent-subtle`, `--signal-candidate*` | words map to time; popover keys |
| Inspector | `ui/inspector.js` | none, one clip, several (planned), invalid field | `--input-*`, `--track-colour` | edits coalesce; invalid not sent |
| History | (WP8) `history.js` | rows, head, future, branch, checkpoint, marker, hover preview | `--accent-subtle` | Restore adds a step |
| Candidates | (WP18) `candidates.js` | open, cut, kept, current | `--signal-candidate*` | ] [ step; preview diagram |
| Status bar | `index.html` `.statusbar`, `app.js` | hints per panel, disconnected | `--text-secondary` | hints follow F6 |
| Toast | `.notice` (`app.js showNotice`) | info, error | `--toast-*` | role status/alert; Undo action |
| Command palette | (WP5) `palette.js` | empty, filtered, no results | `--shadow-dialog`, `--surface-scrim` | focus returns |
| Drop card / overlay | `index.html` `#empty`, `#drop` | empty project, dragging | `--accent`, `--border-strong` | keyboard path: Import button |
| Clip grammar gallery | prototype `screen=gallery` | every signal, both themes | registry | every `SIGNALS` id has a card |
| Theme button | `index.html #theme`, `app.js` | system, light, dark | — | repaints canvases; survives reload |

## 12. How to extend (procedures for implementers)

### 12.1 Add a signal

1. Pick its **channel** from 5.1 whose meaning fits. If none fits, stop and ask:
   a new channel needs a new meaning and the owner's yes.
2. Add semantic tokens for its colours (light and dark) in `tokens.css`: first
   any new primitives (`--p-<family>-<L>`), then the token in **both** dark
   blocks and the light block. Add the token names to `SEMANTIC_TOKENS` in
   `grammar.js`.
3. Add the signal to `SIGNALS` in `grammar.js`: id, channel, meaning (the
   channel's), priority, always, tokens, twin (how it reads without colour),
   when, key, status.
4. If it has a colour that must stand out, add its pair to `pairs()` in
   `ui/tests/tokens.test.js`.
5. Draw it: canvas code reads `theme.resolved.signals.<camelName>` (or a flat
   alias in `theme.js`); CSS uses `var(--signal-…)`. Never a literal.
6. Run `node docs/design/sync-tokens.mjs`, add a card to the prototype's
   `GALLERY`, update section 5 here, run the tests.

### 12.2 Add a theme

1. Write a manifest (10.2) overriding only semantic tokens.
2. Check it with `themeFromManifest`; fix every error.
3. Check contrast: temporarily add it as a block to `tokens.test.js`'s
   `THEMES` (or, once WP35 lands, the built-in check); every pair must pass.
4. To ship it built-in, add it to `tokens.css` as a `:root[data-theme="<name>"]`
   block, add the name to `THEMES` in `theme.js`, and add screenshots.

### 12.3 Add or restyle a component

Use semantic or component tokens only; if a value repeats in two components,
add a component token (layer 3) referencing a semantic one. Reuse the
prototype's class names (`.button`, `.chip`, `.track-header`, `.panel-head`,
`.field`, `.toast`) so the prototype stays the side-by-side reference. Add the
row to section 11.

## 13. Accessibility checklist

- Contrast: all text ≥ 4.5:1 and all meaningful graphics ≥ 3:1 in both themes
  (test-enforced, 190+ pairs).
- No information by colour alone (registry twins, test-enforced).
- Every control reachable by keyboard; visible focus; no traps; F6 regions;
  the timeline canvas has `role="application"` with a label naming its keys.
- Icon-only controls have accessible names; role icons carry the role name.
- Toasts: `role="status"` / `role="alert"`.
- Motion off with `prefers-reduced-motion`.
- Finnish: every string from `en.json`/`fi.json`, +40 % room.

## 14. State of this branch

Built in the editor (`ui/`): tokens in three layers; the grammar registry and
its helpers; theme override (System/Light/Dark); the window grid (top bar,
heads, timeline, transcript dock, sidebar with Inspector over History, status
bar with view tools and key hints); speaker hues; bus groups above their tracks
with spine, band and letter badge; current-lane tint; file zebra, file marks,
seams, clipping caps; restyled ruler, playhead, range flags, gain line rules,
overview, inspector, toasts.

Designed and shown in the prototype only (built with their WPs): sidebar tabs,
transcript, history, candidates, palette, focus mode, collapsed buses, bus
solo, gate, soft cut, drift/free/sync badges, placeholders, takes, notes,
tether, labels, changes view, jobs popover, mode chips other than waveform
height and connection.

Not verified: the app with a real browser in Windows/Linux; screen readers;
real audio playback (never started); F6 and Mod+L interception in Chrome;
the colour-blind simulation was computed (Machado 2009), not checked by
colour-blind users.

## 15. Open questions for the owner

1. **Waveform scale for speech:** linear (today) or dB-shaped? *Recommended:
   dB-shaped for speech and speech-mix tracks, linear for music*: quiet speech
   stays visible in 56 px lanes, and level differences still show.
2. **Spot key:** `=` is zoom in. *Recommended: Spot on Mod+J ("Jump to time").*
3. **Finnish keyboard:** bind `[ ] `` by physical key (Å, ¨, §)? *Recommended:
   yes* (otherwise the candidate keys need Option on a Finnish Mac).
4. **Mod+F:** fade (WP5 table) or find? *Recommended: find in the transcript;
   fade stays G.*
5. **Import key in the browser:** Mod+T cannot be caught by a web page.
   *Recommended: Mod+I now, Mod+T added when the desktop wrapper (WP15) lands.*
6. **Bus solo:** what does S on a bus do? *Recommended: exclusive solo of all
   its member tracks as a set (Shift+Alt adds), shown on the bus and its members.*
7. **Track order under buses:** the timeline gathers a bus's tracks under it,
   but the model keeps its own order. *Recommended: assigning a bus also moves
   the track in the model to the end of that group (one undoable edit), so the
   two orders never differ.*
8. **Role strip:** off on the timeline, on in the clip bin and cards?
   *Recommended: yes* (section 5.5).
