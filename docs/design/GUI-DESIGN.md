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
theme, language and density. URL parameters: `?screen=main|transcript|crosstalk|history|candidates|recording|palette|compare|collapsed|focus|import-drop|import|menu|empty|error|gallery&theme=light|dark|system&lang=en|fi&density=comfortable|compact&width=auto|1024|1280|1440|1920|2560&motion=full|subtle|off&clean=1`. The bar also shows the live count of controls at rest.

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

9. **At rest, only what you use every minute** (owner, 18.10.2026). A
   track header at rest is a name, a role icon, M and S; levels, pickers and
   key chips appear on the current track, on hover and with keyboard focus,
   and everything else is one click away (View menu, inspector sections, the
   palette). So the resting main screen stays within a budget of 25 controls
   (section 16), and a new resting control must replace one.

## 2. The main window

```
┌ top bar 52 ─ project/edit │ ▶ Play  0:12:34.567  [chips only when active]   ↶ ↷  Import  Export  Commands ┐
├ heads 272 ────────────────┬ overview 20 ──────────────────────────────────────┬ sidebar 360 ──────────┤
│ (spacer = overview+ruler) │ ruler 24                                          │ tabs                  │
│ ▾ [A] Voices        M     │ bus row 32 (band)                                 │ Inspector │ History │ │
│ ▌   Anna            M S   │ lane 80: clips, half waveforms                    │ Candidates │ Clip bin│
│ ▌   Ville           M S   │ lane 80                                           │                       │
│ ╰ (spine cap)             │                                                   │ panel body            │
│ ░░ group gap 14 ░░░░░░░░░ │ ░░ plain lane ░░                                  │                       │
│ ▌[B] Theme tune     M S   │ a one-track bus, merged into its track            │                       │
├───────────────────────────┴───────────────────────────────────────────────────┤                       │
│ transcript dock 26vh (min 140, max 60 %)                                      │ action bar (sticky)   │
├ status bar 32: 30 s · Close │ 3 key hints │                saved · View ▾ ──┴───────────────┘
```

Sizes per density (tokens in `ui/tokens.css`; section 16 explains the two densities):

| Region | Comfortable (default) | Compact | Min / max | Resize | At rest |
|---|---|---|---|---|---|
| Top bar | 52 px; buttons 40 px with 44 px hit targets | 38 px; 26 px buttons | fixed | no | always |
| Track header column | 272 px | 216 px | 232 / 380 (180 / 360 compact) | drag (planned) | always |
| Overview strip | 20 px | 20 px | fixed | no | with clips |
| Ruler | 24 px (`RULER_HEIGHT`) | 24 px | fixed | no | always |
| Track lane | 80 px (`DEFAULT_LANE`) | 40 px | 24 / 160 | Shift+= / Shift+-; drag a lane edge | — |
| Bus row | 32 px, one line (`BUS_HEIGHT`) | 24 px | — | — | — |
| Collapsed bus | ribbons: 8 px per member + 8, max 48; one member: 40 px summed | 32 px | — | — | — |
| Group gap | 14 px (`GROUP_GAP`) | 6 px | — | — | — |
| Member indent | 14 px from the spine | 10 px | — | — | — |
| Sidebar | 360 px | 280 px | 280 / 520 (260 / 480) | drag (planned); hide from View | always |
| Transcript dock | 26 vh | 30 vh | 140 px / 60 % | drag (planned); collapses when short | always |
| Status bar | 32 px | 22 px | fixed | no | always |

Rules:

- One screen, no page scroll above the minimum window (section 17).
- Docks are separated by 1 px lines (`--frame-gap`), never by shadows.
- The project block above the headers keeps the transport aligned with the
  timeline's left edge: the eye runs straight down from Play to the playhead.
- **Groups read as blocks:** a bus header sits above its members, the members
  are indented, and a plain gap (no band, no spine) separates each group from
  the next group or from tracks on no bus. The spine ends with a rounded cap at
  the last member.
- **A click anywhere in the lane area sets the play cursor** (section 7.3).

## 3. Panels and components

Each entry: purpose · contents · states. File names are in the component
inventory (section 11).

### 3.1 Top bar

- **Project block:** project name (600) and below it the open edit with its
  length ("Main edit · 58:41", WP21); click or Mod+O opens the edit switcher.
  Today the app shows "kuulas" (no project name in the API yet).
- **Transport:** Play/Stop is the one accent-filled button in the window
  (`--button-primary-bg`), 40 px tall with a 44 px hit target. Its key ("Space")
  appears as a small label under the button on hover and keyboard focus only
  (comfortable), so the button's width never changes. The timecode is 24 px
  (18 compact), 600, tabular numerals, `h:mm:ss.mmm` with the milliseconds in
  `--text-secondary`; Finnish uses the decimal comma (`0:12:34,567`).
- **Mode chips** appear only while something is active, amber `.chip.warn`
  unless noted: speed ≠ 1×, "Group editing off", "Solo: Ville", "Focus:
  Ville" (neutral), connection lost "Reconnecting…" (`.chip.danger`). They never
  truncate; their keys are in the tooltip, not on the chip.
- **Jobs chip:** shown only while a job runs or failed: progress ring + "Transcribing
  2 of 3"; click opens a 320 px popover with one row per job (bar, percent,
  Cancel; a failed job's error and Retry).
- **Undo/Redo** (ghost icon buttons, tooltips "Undo · ⌘Z"), **Import** (Mod+I in
  the browser, see 9), **Export** (Mod+E), **Commands** (the palette, Mod+K; the
  label hides below 1100 px).

States: empty project: Play and Undo disabled, Import becomes primary.

### 3.2 Track headers and bus headers

**At rest a track header shows four things:** the role icon, the name, M and
S. Everything else is one step away:

| Thing | At rest (comfortable) | Shows when | Also in |
|---|---|---|---|
| Gain and pan sliders | hidden (space kept, so nothing jumps) | the track is current (↑/↓), on hover, while focus is inside | the inspector's track section (planned) |
| Bus picker (letter + chevron) | not in the layout: the name gets its width | current, hover, focus | inspector; drag the header onto a group |
| Key chips | none | tooltips ("Mute · ⇧M") | palette, status bar hints |
| Default/custom marker | — | after a double-click toggle (section 21) | tooltip "was −2.5 dB" |

Compact shows everything at once, as before: both rows, the bus picker, the
values.

Layout of a track header (lane height; rows of 28 px in comfortable):

- row 1 (aligned with the clip names at the top of the lane): role icon (mic =
  speech, note = music; the role name is the tooltip and
  the accessible name) · name (600; long names are shortened **in the middle**,
  "Anna · varam…foni", with the full name in the tooltip and accessible name;
  double-click renames) · [bus picker] · M · S
- row 2 (current/hover): gain slider (−60…+12 dB, neutral grey track, value
  "−1.5 dB") · pan slider (84 px, "L 10" / "C" / "R 10"; Finnish V/K/O)
- left edge: the **bus spine** (4 px, full height, bus colour) for members of a
  bus, and the **track pill** (3 × 20 px, rounded, the speaker hue), level with
  the name. Members are indented 14 px from the spine, so the bus row reads as
  the outer level.
- current track: `--header-bg-current` across header and lane. Muted: M filled
  neutral. Not heard because of solo: name and controls at 55 %, M dashed,
  tooltip "not heard: solo". Solo: S amber, plus the "Solo" chip.

**Bus row** (one short line: 32 px, 24 compact, flush with the spine, on the
bus band): disclosure chevron · letter badge (A, B, …) · name (600, bus text
colour) · [member count when collapsed] · [bus fader on hover/focus] · M ·
[S on hover/focus]. The **bus fader** is a different control from the track
sliders: a 5 px track filled in the bus colour, labelled "Bus" ("Väylä"), shown
inline on hover or focus; bus pan and the rest live in the inspector's Bus
section (section 6). Double-click the row, click the chevron, or Alt+Mod+← / Alt+Mod+→
on a member collapses or expands it.

**A one-track bus** is merged into its track's header by default: the badge
before the role icon, the spine, no bus row (section 6).

### 3.3 Ruler and overview

- **Ruler:** `--ruler-bg`, labels 11 px monospace in `--ruler-text` every
  ≥ 80 px (1-2-5 steps, `ruler.js`), major ticks 9 px, minor 4 px in
  `--ruler-tick`. Flags live in the ruler: in/out (accent triangles pointing
  inwards), candidates ("cut? 2.4 s" on a `--signal-candidate-fill` band with a
  3 px top edge), markers and chapters (WP19h: a notch and the name). A flag
  hides the time labels under it rather than overlapping them.
- The playhead's cap is a 11 px pentagon in `--playhead`; the start of the last
  play is a hollow triangle in `--play-start` (where Stop-and-return would go).
- **Overview strip:** one thin row per track in the track's wave colour at 60 %,
  drawn only where that track sounds (`ui/overview-segments.js`): a gap wherever
  it is silent, whether there is no clip, the clip or track is muted, Auto-Silence
  closed the stretch, or the Auto-Silence preview would. No lock, outline or
  hatching: bar = heard, gap = not. Sibling ticks, the visible part as a box
  (1.5 px accent outline, `--selection-range` fill) and the playhead as a 1 px
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

Tabs: Inspector · Candidates (count pill) · Clipboard · Markers · History,
then the hide-panel x. **One row at every width, labels never wrap or get an
ellipsis** (owner, 2026-10-21). `ui/side-tabs-model.js` picks a step from the
measured width the strip needs and the room it has (`data-tabs` on
`.side-tabs`):

| Step | When | Looks like |
|---|---|---|
| full | all names plus whole keys fit | "Inspector Alt+1" (mac "⌥1"), dimmed key |
| tight | full does not fit | same names, key as a digit, 6 px padding |
| compact | tight does not fit (the 260-280 px minimum, Finnish names) | only the selected tab keeps its name; the others show only their key digit |

The key hint is on every tab at every step.
The selected tab is marked by colour and underline only (no bold), so it never
changes width. Every tab has the tooltip "Name (Alt+n)", an accessible name
(the label, also in compact) and `aria-keyshortcuts`; the key is the user's if
rebound. Alt+1..Alt+5 need no AltGr or Shift+digit. In compact the Candidates
count pill shows only on the selected tab.

**Inspector** (selected clip): the title block (4 px hue bar, the clip's label
at 17 px, then "Anna.wav · Part 3 of 3 · Anna", the bus line with badge and the
file mark), then **collapsible sections** (native `<details>`): **Level** and
**Sync** open by default; **Fades**, **Source**, **Voice** and **Details**
closed, each showing a one-line summary on the right of its heading ("0 · 30 ms",
"Part 3 of 3", "Speech · clean"). What the user opens or closes is remembered
per user (`kuulas.inspector.sections`; `inspector.js openSections`, tested).

- Level: clip gain, pan (inputs 84 px, right-aligned; key chips on focus only),
  mute. Double-click or Shift+Enter toggles default/custom (section 21).
- Sync: "Group 1 · in sync with Anna, Pekka" (`--ok-text`) or the drift block
  (cause, Resync R, Free from sync U).
- **Source** (section 18): a mini map of the whole recording (used, soft-cut,
  unused, this clip outlined) and "Other clips from this recording (n)": rows
  "2/5 · Anna · 1:21–1:22 · Anna · 12:31" that jump to the clip.
- Invalid input: 1 px danger border + ring, message under the field; not sent.
- Empty: "Select a clip to see its level, fades and sync." + a hint.

**History**, **Candidates**: as in 3.6 before, with rows 32 px tall in
comfortable. **Clip bin** (WP17): **grouped by recording**: a recording header
(file mark, file name, clip count, person) with its clips under it, numbered
"1/3, 2/3 …" by source position (section 18).

### 3.7 Status bar

At rest: the span ("30 s", the zoom readout) · the Close/Wide toggle (Z) |
**at most three key hints for the focused panel** (timeline: "B split · X
cut · Q W trim"; transcript: "⌫ cut words · Enter correct · ⌥D mark") |
spacer | save state ("✓ All changes saved"; disconnected: "Saved up to 19.58 ·
edits paused") | **View ▾**.

The **View menu** (a native popover above the status bar's right end; Esc or
an outside click closes it) holds everything else about the view: zoom out /
in and Fit (Shift+Z), waveform mode, lane height −/+, follow mode, **density**
(comfortable / compact), **animation** (full / subtle / off), theme (system /
light / dark).

### 3.8 Messages (toasts)

Bottom centre, 16 px above the status bar, max 560 px, `--toast-bg` with
`--toast-shadow`, 3 px left edge (accent = info/success, danger = error).
Content: what happened ("Cut 2.4 s on 4 tracks") + actions (Undo ⌘Z, Change…,
Redo) + close ×. Success and info vanish after 6 s unless hovered or focused;
errors stay until closed. Errors say how to fix it ("The first 12:40 can still
be imported." · "Import the first 12:40" · "Show file"). One toast at a time;
a newer one replaces an older one of the same kind. `role="status"` for
info, `role="alert"` for errors.

### 3.9 Command palette (Mod+K): a command bar docked over the sidebar

**Picked: a docked command bar, not a floating modal** (owner, 18.10.2026: the
centred modal with a scrim covered the timeline). It opens directly under the
top bar, right-aligned, **exactly over the sidebar column** (its width:
`--sidebar-w`, 280–360 px), and grows downward at most to the status bar. Why
docked: the sidebar is the one region you do not need while choosing a command;
the lanes, the ruler, the playhead and the transcript stay visible and
clickable, playback continues, and the playhead can be moved while it is open.

- No scrim at all. `--shadow-raised` and a 1 px left border separate it.
- A 48 px search field, results in groups ("Recent" first when empty), rows of
  32 px: icon, name with matched letters underlined, key chips; the remembered
  default under the name in tertiary ("MP3 128 kbps · mono", WP35).
- Enter runs and closes; Esc closes; focus returns where it was.
- **A command that needs a target asks inline**, inside the bar, below the
  results: "Spot clip to time" shows a time field ("12:40.500", "Type a time and
  press Enter; Esc cancels."). It never opens a dialog over the timeline.
- Below 1100 px the sidebar column holds the transcript too; the bar then
  covers that column only.

### 3.10 Other surfaces (designed here, built with their WP)

- **Export dialog (WP11):** a 520 px dialog: format segmented control
  (WAV / FLAC / MP3), what (whole edit / selection / each track), loudness
  target, the destination with the next version name ("Pistejulkaisu v3.mp3"),
  the music-report and placeholder warnings as inline notices with "Show
  them". Enter exports with the shown settings; the plain key (Mod+E) skips
  the dialog when settings are remembered (WP35).
- **Music report (WP25):** File > Export > Music report… (no default key; the
  Finnish layout leaves none free). A modal dialog on the shared form and
  button rules (`FORMS.md`, `BUTTONS.md`), 960 px wide, for the open edit.
  Top to bottom: a one-line scope note (times are programme times in whole
  seconds, part-seconds rounded up), the summary line (pieces and total music
  time), the warnings (one line per piece missing a title or an artist, saying
  which; the rows are also tinted), the preview table (order, title, artist,
  composer, publisher, programme start, duration, background/featured; the
  title falls back to the file name) in a focusable scroller with a sticky
  header, so a long report scrolls and the dialog does not. Footer: Copy as
  table (tab separated, ISRC, file name and out time included), Save CSV…,
  Save HTML… (all `.footer-start`: they keep the dialog open), Close
  (primary, last). The files are downloads named `<project> music-report.csv`
  / `.html` by the server; the browser (or the desktop window's download)
  chooses the folder and never overwrites. An edit with no music shows "No
  music in this edit" and the reason (no music track, muted, no clips, or
  silenced). The server builds the report from a snapshot of the edit, so
  the preview does not hold the session lock; the dialog shows "Building the
  report…" meanwhile.
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

The light palette is a soft mid-light grey with a slight cool bias, not white
(owner, 2026-10-19: "more contrasty, background less white"). Steps, dark to
light: app frame `#b4bbc1`, hover/active `#c1c7cc` / `#b5bcc2`, panel `#cfd4d8`,
lane `#d8dcdf` (a little lighter than the panel so waveforms sit on the
lightest ground), inputs `#e3e7ea`, popovers `#e9ecee`. Clip bodies stay light
tints, so a clip reads as an object on the grey lane. Targets, pinned by
`ui/tests/theme-contrast.test.js` for the light theme: `--text` ≥ 7:1 on every
surface, secondary and status text ≥ 4.5:1 (secondary ≥ 7 on panel, lane,
raised), `--border-strong`, focus ring, ruler ticks ≥ 3:1, icons and lines
(secondary text, gain and automation lines, play-start) ≥ 4.5:1, playhead ≥ 3.5:1
on the lane, waveforms and clip edges ≥ 3:1 on the lane, clip labels ≥ 7:1 on
the body, the closed-gate veil equal to the lane colour. Dark is unchanged.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--surface-app` | `#b4bbc1` | `#0f1214` | behind everything; the 1 px gaps between docks |
| `--surface-lane` | `#d8dcdf` | `#13171a` | timeline background |
| `--surface-lane-current` | `#bcdcd5` | `#172225` | the current track's lane and header (↑/↓ cursor) |
| `--surface-panel` | `#cfd4d8` | `#171b1e` | headers, panels, top and status bars |
| `--surface-raised` | `#e9ecee` | `#1e2327` | popovers, palette, toasts (with --shadow-raised) |
| `--surface-sunken` | `#e3e7ea` | `#101316` | inputs, wells, key chips |
| `--surface-hover` | `#c1c7cc` | `#212729` |  |
| `--surface-active` | `#b5bcc2` | `#283034` | pressed controls, count pills |
| `--surface-scrim` | `rgb(16 24 28 / 0.32)` | `rgb(0 0 0 / 0.5)` | behind modal dialogs |
| `--border-subtle` | `#b3bac0` | `#22282c` | lane separators, list dividers |
| `--border` | `#848e96` | `#2d3539` | panel edges, controls at rest |
| `--border-strong` | `#55616a` | `#66727a` | input outlines: >= 3:1 on panels |
| `--text` | `#0e1316` | `#e7ecee` |  |
| `--text-secondary` | `#263036` | `#aab4b9` |  |
| `--text-tertiary` | `#35414a` | `#8f9aa0` | still >= 4.5:1: body text, never decoration |
| `--text-disabled` | `#7d878d` | `#566066` | disabled only (exempt from contrast) |
| `--text-on-accent` | `#ffffff` | `#04211d` |  |
| `--accent` | `#07705f` | `#3dc9b3` | primary buttons, focus, range edges, the overview box |
| `--accent-hover` | `#05604f` | `#5ad6c2` |  |
| `--accent-text` | `#04503f` | `#5ad6c2` | accent-coloured text on panels |
| `--accent-subtle` | `#98cdc2` | `#133a35` | selected rows, selected words |
| `--focus-ring` | `#055e51` | `#5ad6c2` |  |
| `--warn` | `#9c6200` | `#f0b54a` | fills and strokes: solo, speed chip |
| `--warn-text` | `#633a00` | `#f3c165` |  |
| `--warn-subtle` | `#efd9ad` | `#3a2c12` |  |
| `--danger` | `#b82c1a` | `#ff776b` |  |
| `--danger-text` | `#8a1f12` | `#ff8a7f` |  |
| `--danger-subtle` | `#efc9c2` | `#3d1d1b` |  |
| `--ok` | `#167a40` | `#6fd39a` |  |
| `--ok-text` | `#0b5530` | `#7fdca6` |  |
| `--shadow-raised` | `0 6px 20px var(--p-gray-22-a14), 0 0 0 1px var(--p-gray-22-a8)` | `0 8px 24px var(--p-black-a45), 0 0 0 1px var(--p-gray-32)` |  |
| `--shadow-dialog` | `0 18px 48px var(--p-gray-22-a22), 0 0 0 1px var(--p-gray-22-a8)` | `0 20px 56px var(--p-black-a60), 0 0 0 1px var(--p-gray-32)` |  |
| `--playhead` | `#c92f1b` | `#ff6b57` |  |
| `--play-start` | `#35414a` | `#8f9aa0` | where the last play started (hollow mark) |
| `--selection-range` | `rgb(7 112 95 / 0.22)` | `rgb(61 201 179 / 0.16)` | in/out band on the scoped lanes |
| `--gain-line` | `#0e1316` | `#e7ecee` |  |
| `--automation-line` | `#263036` | `#aab4b9` |  |
| `--ruler-text` | `#263036` | `#aab4b9` |  |
| `--ruler-tick` | `#66717a` | `#4a555b` |  |
| `--signal-selected` | `#0b1114` | `#ffffff` | 2 px outline: neutral, works on every hue |
| `--signal-partner` | `#263036` | `#aab4b9` | dashed: what a move takes along |
| `--signal-muted-hatch` | `rgb(14 19 22 / 0.38)` | `rgb(231 236 238 / 0.22)` |  |
| `--signal-muted-opacity` | `0.35` | `0.35` |  |
| `--signal-unheard-opacity` | `0.45` | `0.45` |  |
| `--signal-unused-opacity` | `0.5` | `0.5` |  |
| `--signal-placeholder` | `#263036` | `#aab4b9` | dashed outline of narration placeholders |
| `--signal-provisional` | `#35414a` | `#8f9aa0` |  |
| `--signal-candidate` | `#b82c1a` | `#ff776b` | stripes and edges of cut candidates |
| `--signal-candidate-fill` | `rgb(184 44 26 / 0.14)` | `rgb(255 119 107 / 0.13)` |  |
| `--signal-soft-cut` | `#b82c1a` | `#ff776b` | a cut that kept its gap: edges and hatch |
| `--signal-soft-cut-fill` | `rgb(184 44 26 / 0.1)` | `rgb(255 119 107 / 0.09)` |  |
| `--signal-gate` | `#d8dcdf` | `#13171a` | the veil over a closed gate (lane colour) |
| `--signal-gate-opacity` | `0.7` | `0.7` |  |
| `--signal-damaged` | `#b82c1a` | `#ff776b` |  |
| `--signal-damaged-fill` | `#efc9c2` | `#3d1d1b` |  |
| `--signal-removed` | `#b82c1a` | `#ff776b` |  |
| `--signal-removed-fill` | `rgb(184 44 26 / 0.14)` | `rgb(255 119 107 / 0.13)` |  |
| `--signal-added` | `#167a40` | `#6fd39a` |  |
| `--signal-drift` | `#b82c1a` | `#ff776b` | solid badge with the offset |
| `--signal-drift-text` | `#ffffff` | `#1a0c0b` |  |
| `--signal-clipping` | `#b82c1a` | `#ff776b` | the cap on a clipped column |
| `--signal-file-mark` | `#e9ecee` | `#0f1214` | file mark chip background |
| `--signal-file-mark-text` | `#0e1316` | `#e7ecee` |  |
| `--signal-free` | `#263036` | `#aab4b9` |  |
| `--signal-seam` | `#263036` | `#aab4b9` | hairline (split) and notch (jump cut) |
| `--signal-takes` | `#263036` | `#aab4b9` |  |
| `--signal-note` | `#9c6200` | `#f0b54a` |  |
| `--signal-sync` | `#263036` | `#aab4b9` |  |
| `--signal-tether` | `#263036` | `#aab4b9` |  |
| `--signal-sibling` | `#07705f` | `#3dc9b3` | corner brackets: same recording as the selection |
| `--signal-collateral` | `#b82c1a` | `#ff776b` | what a transcript cut also removes |
| `--signal-collateral-fill` | `rgb(184 44 26 / 0.2)` | `rgb(255 119 107 / 0.2)` |  |
| `--signal-preview` | `#07705f` | `#3dc9b3` | a Compare preview is playing (not committed) |
| `--role-speech` | `#263036` | `#aab4b9` | strip pattern: solid |
| `--role-music` | `#7a715e` | `#8e8572` | strip pattern: dotted |

Contrast, checked by the test (WCAG 2.2: text ≥ 4.5, graphics and outlines ≥ 3):

| Text token | on panel (light / dark) | on lane | on raised |
|---|---|---|---|
| `--text` | 12.5 / 14.5 | 13.6 / 15.1 | 15.8 / 13.3 |
| `--text-secondary` | 9.0 / 8.2 | 9.8 / 8.5 | 11.4 / 7.5 |
| `--text-tertiary` | 7.0 / 6.0 | 7.6 / 6.3 | 8.8 / 5.5 |
| `--accent-text` | 6.3 / 9.8 | 6.8 / 10.2 | 8.0 / 8.9 |
| `--warn-text` | 6.6 / 10.4 | 7.1 / 10.8 | 8.3 / 9.5 |
| `--danger-text` | 6.2 / 7.6 | 6.7 / 7.9 | 7.7 / 6.9 |
| `--ok-text` | 6.0 / 10.5 | 6.5 / 10.9 | 7.5 / 9.6 |
| `--text-on-accent` on `--accent` | 6.0 / 8.2 | | |
| `--focus-ring` on `--surface-panel` | 5.2 / 9.8 | | |
| `--border-strong` on `--surface-panel` | 4.3 / 3.5 | | |
| `--playhead` on `--surface-lane` | 3.9 / 6.4 | | |
| `--signal-selected` on `--track-0-body` | 17.2 / 15.7 | | |
| `--signal-drift-text` on `--signal-drift` | 6.2 / 7.4 | | |

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
| 0 | edge | `#1b589e` | `#689bdb` | edge/lane 5.2 / 6.3 |
| 0 | label | `#164781` | `#b9daff` | label/body 8.4 / 10.9 |
| 1 | wave | `#946000` | `#fac463` | wave/body 4.8 / 9.9; wave/alt 4.2 / 8.1 |
| 1 | body | `#fbf2e6` | `#2a2112` |  |
| 1 | body-alt | `#f3e2cb` | `#3c2f19` |  |
| 1 | edge | `#a06700` | `#cfa354` | edge/lane 3.4 / 7.7 |
| 1 | label | `#693c00` | `#f0d3a3` | label/body 8.4 / 11.0 |
| 2 | wave | `#ad456b` | `#df7a9b` | wave/body 4.9 / 5.6; wave/alt 4.2 / 4.6 |
| 2 | body | `#ffeff3` | `#2f1d22` |  |
| 2 | body-alt | `#f8dae2` | `#432931` |  |
| 2 | edge | `#a9496b` | `#d6809c` | edge/lane 4.0 / 6.4 |
| 2 | label | `#742945` | `#ffc5d5` | label/body 8.8 / 10.8 |
| 3 | wave | `#00789d` | `#61e3ff` | wave/body 4.6 / 10.4; wave/alt 4.0 / 8.5 |
| 3 | body | `#e7f7fc` | `#12262e` |  |
| 3 | body-alt | `#ccebf5` | `#193641` |  |
| 3 | edge | `#0084a9` | `#50b9df` | edge/lane 3.1 / 8.0 |
| 3 | label | `#003f56` | `#a6e2fb` | label/body 10.4 / 11.1 |
| 4 | wave | `#643185` | `#a57fd0` | wave/body 8.1 / 5.0; wave/alt 7.0 / 4.1 |
| 4 | body | `#f7f0fd` | `#271f2e` |  |
| 4 | body-alt | `#eaddf5` | `#382c41` |  |
| 4 | edge | `#633481` | `#9c78c4` | edge/lane 6.5 / 5.1 |
| 4 | label | `#5a3473` | `#e6cbfb` | label/body 8.7 / 10.8 |
| 5 | wave | `#4e8626` | `#96c166` | wave/body 4.0 / 7.5; wave/alt 3.5 / 6.1 |
| 5 | body | `#eef6ea` | `#1e2616` |  |
| 5 | body-alt | `#d9e9d1` | `#2b3620` |  |
| 5 | edge | `#51852f` | `#94b96d` | edge/lane 3.2 / 8.1 |
| 5 | label | `#1f4106` | `#c8e1b1` | label/body 10.5 / 11.1 |
| music | wave | `#76694f` | `#b5aa92` | wave/body 4.7 / 7.0; wave/alt 4.1 / 5.7 |
| music | body | `#f2f0ec` | `#24211c` |  |
| music | body-alt | `#e4e1da` | `#33302a` |  |
| music | edge | `#7a715e` | `#8e8572` | edge/lane 3.5 / 4.9 |
| music | label | `#4f4735` | `#d8d0bf` | label/body 8.1 / 10.5 |

CVD separation, light, min OKLab ΔE×100 between waveform colours (first four / all six): normal 14.9 / 13.5, deuteranopia 11.0 / 5.4, protanopia 10.5 / 1.8, tritanopia 7.8 / 7.1.

CVD separation, dark, min OKLab ΔE×100 between waveform colours (first four / all six): normal 19.6 / 10.8, deuteranopia 14.9 / 3.6, protanopia 11.3 / 5.1, tritanopia 15.1 / 11.8.

The order (blue, amber, rose, sky, violet, green) was searched so the first
four, the common case, stay apart under deuteranopia, protanopia and
tritanopia (values above). Hues 5 and 6 are close under protanopia in light;
they lean on the twins (track name, pill position, file name), which is why no
hue is ever the only cue.

### 4.4 Bus colours (group identity)

Eight hues, deliberately lower in chroma than the speaker hues so a spine
never reads as a speaker: 1–4 muted, 5–8 (for nested buses, section 25) at a
different lightness tier. Letters A, B, C … (A1, A1a when nested) are the twin.

| Bus | Letter | Spine light / dark | Text light / dark | Checked text/panel, spine/panel (light; dark) |
|---|---|---|---|---|
| 1 | A | `#5970a4` / `#8ba4db` | `#374c79` / `#bed1f9` | 5.7, 3.3; 11.3, 7.0 |
| 2 | B | `#797435` / `#aca868` | `#544f11` / `#d6d4a7` | 5.6, 3.2; 11.4, 7.1 |
| 3 | C | `#8e5f89` / `#c391be` | `#653c62` / `#e8c3e4` | 5.9, 3.4; 11.0, 6.7 |
| 4 | D | `#9b6147` / `#d29478` | `#713e26` / `#f4c5b1` | 5.8, 3.4; 11.1, 6.8 |
| 5 | E | `#005c4a` / `#91dcc7` | `#005545` / `#b2e4d5` | 5.9, 5.3; 12.3, 10.9 |
| 6 | F | `#514279` / `#cec1fa` | `#4b3e6e` / `#d9d1f9` | 6.4, 5.8; 11.9, 10.4 |
| 7 | G | `#664600` / `#e6c58f` | `#5e4205` / `#ebd4af` | 6.2, 5.8; 12.0, 10.5 |
| 8 | H | `#76363d` / `#fab6ba` | `#6c343a` / `#fac9cc` | 6.4, 5.9; 11.8, 10.3 |

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

- Spacing on a 4 px grid: 2, 4, 6, 8, 12, 16, 24, 32 (`--space-1…8`). Component
  padding comes from the density tokens `--pad-panel`, `--pad-inline`,
  `--row-gap`, `--section-gap` (section 16).
- Forms: a fixed label column (`--form-label-w` in dialogs, `--form-label-w-panel` in
  panels) and one field column; the rules are in `FORMS.md`.
- Radii: 2 (badges, key chips) · 4 (controls) · 6 (popovers, cards, toasts) ·
  10 (dialogs) · pill (chips). **Clips are square**: crisp edges read as edit points.
- Elevation: flat docks; `--shadow-raised` for popovers, toasts, the command
  bar; `--shadow-dialog` for dialogs over `--surface-scrim`.
- Density: **comfortable** (default, roomy) and **compact** (the earlier, denser
  values); section 16.

### 4.7 Motion

See section 20 (the motion language). Durations: `--dur-fast` 90 ms,
`--dur-base` 140 ms, `--dur-layout` 120 ms, `--dur-slow` 240 ms, `--dur-flash`
600 ms; easing `--ease-standard`.

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

| # | Signal | Channel · meaning | Priority | At rest | Light | Dark | Non-colour twin | When shown | Keys | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **speaker** | hue · identity | 0 (always) | shown | track/bus/label hues | track/bus/label hues | track name in the header and file name on the clip; the header swatch is a short pill | always | — | built |
| 2 | **file-zebra** | tone · identity | 0 (always) | shown | track/bus/label hues | track/bus/label hues | file mark chip and file name on each clip; a seam marks every change of file | neighbouring clips on one track come from different files | — | built |
| 3 | **selected** | weight · selection | 0 (always) | shown | `#0b1114` | `#ffffff` | 2 px outline (shape), plus the inspector shows the clip | the clip is selected | click, Tab, Mod+A | built |
| 4 | **placeholder** | dash · reality | 0 (always) | shown | `#263036` | `#aab4b9` | dashed outline, no waveform, the script text in italics inside | narration placeholder (WP43) | T | prototype |
| 5 | **damaged** | pattern · absence | 0 (always) | shown | `#b82c1a` `#efc9c2` | `#ff776b` `#3d1d1b` | cross-hatch, a '!' badge with the word 'damaged', and the reason on hover | media that cannot be read there (plays silence) | — | prototype |
| 6 | **drift** | badge · facts | 0 (always) | shown | `#b82c1a` `#ffffff` | `#ff776b` `#1a0c0b` | solid badge with the offset in text ('−312 ms'), cause on hover | undecided drift from the sync group (WP19a) | R resyncs, U frees | prototype |
| 7 | **bus** | spine · grouping | 0 (always) | shown | track/bus/label hues | track/bus/label hues | letter badge (A, B, C) in the bus header, the transcript and the inspector | a track is on a bus: the spine runs from the bus header through its tracks | — | built |
| 8 | **bus-band** | band · grouping | 0 (always) | shown | — | — | drawn only together with the spine (the band is a tint of the spine's colour) | behind a bus's header and member lanes | — | built |
| 9 | **collateral** | pattern · absence | 0 (always) | only while words are selected in the transcript | `#b82c1a` `rgb(184 44 26 / 0.2)` | `#ff776b` `rgb(255 119 107 / 0.2)` | other speakers' words struck through with a wavy underline, 'also removed' in the word pop-up, the stretch hatched and the affected clips outlined on the timeline | a transcript selection whose cut would also remove other tracks' words or audio | X cuts on all tracks (ripple); Backspace deletes on this speaker only, keeping the gap | prototype |
| 10 | **ribbons** | ribbon · activity | 0 (always) | shown | — | — | one strip per member in its position (top to bottom = header order), filled where the track has sound; the tooltip names the track and clip | a collapsed bus with two or more members (one member keeps its summed waveform) | Alt+Mod+← collapses, Alt+Mod+→ expands | prototype |
| 11 | **preview** | dash · reality | 0 (always) | only while the Compare bar is open | `#0a7a6b` | `#3dc9b3` | a dashed top band over the compared range with the slot letter ('A', 'B') in it, and the Compare bar itself | a Compare preview is playing: nothing is committed until 'Keep this one' | ` flips, 1–4 pick a slot, Enter keeps, Esc discards | prototype |
| 12 | **muted** | opacity · audibility | 1 (always) | shown | `rgb(19 25 28 / 0.28)` `0.35` | `rgb(231 236 238 / 0.22)` `0.35` | diagonal hatch over the clip; M pressed in the header for a muted track | the clip is muted | N | built |
| 13 | **unheard** | opacity · audibility | 1 (always) | shown | `0.45` | `0.45` | header says 'not heard: solo' in its tooltip and the M button turns dashed | another track is soloed, or this track is muted | Shift+S, Shift+M | prototype |
| 14 | **gate** | opacity · audibility | 1 (always) | shown | `#d8dcdf` `0.7` | `#13171a` `0.7` | the same diagonal hatch as a muted clip (--signal-muted-hatch), the waveform under the band drawn flat (a 1 px floor line) and a small gate tick at each edge; hover says 'Mic closed by Auto-Silence' and offers 'Open this stretch' | Auto-Silence: one merged gate per track closes the mic (WP44); a per-lane toggle shows or hides it | Alt+Mod+P runs Auto-Silence | prototype |
| 15 | **candidate** | pattern · absence | 1 (always) | shown | `#b82c1a` `rgb(184 44 26 / 0.14)` | `#ff776b` `rgb(255 119 107 / 0.13)` | diagonal stripes across the group's lanes and a 'cut?' flag in the ruler | an open cut candidate (WP18) | D, ] [, Enter, Backspace | prototype |
| 16 | **soft-cut** | pattern · absence | 1 (always) | shown | `#b82c1a` `rgb(184 44 26 / 0.1)` | `#ff776b` `rgb(255 119 107 / 0.09)` | hatch plus a solid 2 px edge at each end in the cut colour, and the word 'cut' when wide enough; the context menu says 'Restore' | Delete (Backspace): audio removed in place, the gap kept, restorable; 'Show cuts' (on by default) hides or shows them | Backspace (Delete); Restore from the menu or the palette | prototype |
| 17 | **removed** | pattern · absence | 1 (always) | only in the changes view (WP31) | `#b82c1a` `rgb(184 44 26 / 0.14)` | `#ff776b` `rgb(255 119 107 / 0.13)` | a ghost outline with hatch and a '−' glyph | changes view (WP31): audio in A that is gone in B | Alt+Mod+D, ] [ | planned |
| 18 | **added** | bar · change | 1 (always) | only in the changes view (WP31) | `#1e8a4c` | `#6fd39a` | a 3 px bar on the clip's left and right edges and a '+' glyph | changes view (WP31): audio in B that was not in A | Alt+Mod+D, ] [ | planned |
| 19 | **provisional** | dash · reality | 2 (always) | only after 150 ms without the engine's confirmation | `#5c6870` | `#8f9aa0` | short dashes (2 on, 2 off) on the outline | an edit is shown but the engine has not confirmed it after 150 ms | — | prototype |
| 20 | **partner** | scope · edit scope | 2 (always) | only while a clip is selected | `#263036` | `#aab4b9` | dashed 1 px outline inset 2 px, neutral | a clip is selected: its sync partners that a move takes along (WP19a) | E toggles group editing | prototype |
| 21 | **clipping** | cap · level | 2 | shown | `#b82c1a` | `#ff776b` | a 3 px block on top of the clipped column (shape) and a line in the inspector | a peak at or above −0.1 dBFS | — | built |
| 22 | **file-mark** | badge · facts | 3 | shown | `#e9ecee` `#0e1316` | `#0f1214` `#e7ecee` | two characters from the content hash; the same on every track | a track holds clips from more than one file | — | built |
| 23 | **sibling** | bracket · relation | 3 (always) | while a clip is selected, or hovered with Alt held | `#0a7a6b` | `#3dc9b3` | corner brackets on every other clip of the same recording, a tick in the overview, and 'part 2 of 5' in the inspector | the selected clip's recording has other clips in the edit (any track) | Alt+hover | built |
| 24 | **free** | badge · facts | 4 | shown | `#263036` | `#aab4b9` | outlined badge with an unlinked-chain glyph and '+300 ms · free' | a clip freed from its sync group on purpose (U) | U | prototype |
| 25 | **seam-jump** | seam · joins | 4 | shown | `#263036` | `#aab4b9` | a small V notch top and bottom at the join (shape) | two clips of one file meet but audio between them was removed; hover offers 'Put back' (a ripple cut) | Tab stops here | built |
| 26 | **takes** | badge · facts | 5 | shown | `#263036` | `#aab4b9` | stacked top-right corner (two offset edges) and '2/3' | a take set (WP19e) | Alt+] / Alt+[ | prototype |
| 27 | **note** | notch · annotation | 5 | shown | `#b97a00` | `#f0b54a` | a triangular notch in the top edge; the text on hover | a note or marker on the clip's audio | M | prototype |
| 28 | **unused** | opacity · audibility | 6 | only in the clip bin and on cards | `0.5` | `0.5` | the clip bin lists it under 'not in the programme' | clip bin and cards: material not used in the open edit | — | planned |
| 29 | **sync** | badge · facts | 6 | only on the selected clip and its partners | `#263036` | `#aab4b9` | chain glyph and the group number ('⛓ 1') | on the selected clip and its partners only; never on every clip | Y marks in sync | prototype |
| 30 | **tether** | line · attachment | 6 | shown | `#263036` | `#aab4b9` | a thin line from the clip's start down to its anchor, ending in a dot | a connected clip (WP19b) | Alt+Mod+C | planned |
| 31 | **label** | badge · facts | 7 | shown | track/bus/label hues | track/bus/label hues | a square flag in the top-right corner; its name on hover and in the inspector | the user gave the clip a label colour (never set automatically) | — | planned |
| 32 | **seam-split** | seam · joins | 8 | shown | `#263036` | `#aab4b9` | a 1 px hairline (shape) | two clips of one file meet with nothing removed between them | — | built |
| 33 | **role** | strip · role | 9 | only in the clip bin and on cards | `#263036` `#263036` `#7a715e` | `#aab4b9` `#aab4b9` `#8e8572` | strip pattern: solid speech, dotted music; role icon in the header | off on the timeline (the header says it); on in the clip bin and cards | — | prototype |

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
| Look (since 2026-10-21, [SILENCE-VISUALS.md](SILENCE-VISUALS.md)) | waveform outline only (no fill), body toned down (`--signal-silent-body`), no hatch, no icon | waveform outline only under the stretch, body toned down, a padlock (`--signal-gate-lock`) at the left of its visible part; no hatch, so clip borders stay visible | hatch in the cut colour, `--signal-soft-cut-fill`, solid 2 px cut-colour edges, "cut" when wide |
| Wording | "Mute clip" / "Unmute" (N) | hover "Mic closed by Auto-Silence" · click "Open this stretch" | "Delete" (Backspace; keeps the gap, owner 18.10.2026) · "Restore" (ripple cuts made with X: "Put back" on the notch) |
| Visibility | always | per-lane show/hide toggle (lane context menu and palette) | "Show cuts" toggle, on by default |

### 5.5 What shows at rest (checked at the comfortable sizes)

Every signal now says in the registry whether it shows at rest (`atRest`,
tested). Checked at 80 px lanes and 14 px text; dropped from the resting view
because they were noise there:

| Was shown at rest | Now | Why |
|---|---|---|
| Bus band behind every member lane | only on the bus row (and the header column spine) | at 80 px a tinted block per group dominated; the group gap now says "group" |
| Stripes across all lanes for every open candidate | faint fill and 1 px edges; stripes only on the current candidate | stripes over 80 px lanes were the loudest thing on screen |
| Envelope dots | only on the selected clip (the gain line itself stays when gain ≠ 0) | dots on every clip with an envelope read as noise |
| Ducking value label ("ducking −12 dB") | only on the current track | the line itself carries the shape |
| Sync badge, partner rings | already only with a selection | — |
| Role strip | already off on the timeline | the header icon says it |
| Key chips beside buttons and fields | on hover and focus only | 13 chips at rest became 4 |

Kept at rest because they are cheap and informative: speaker hue, file zebra
and file mark (only on tracks with 2+ files), seams, clipping caps, drift
badges, damage, outline-only silent stretches with their padlocks, soft cuts, placeholders, collapsed-bus
ribbons.

## 6. Buses

- **Position:** a bus is a group header *above* its member tracks, like a
  folder (`lanes.js layoutRows`): it appears where its first member would be,
  its members gather under it in track order, tracks on no bus keep their
  place, and buses with no members go last. A **group gap** (14 px, 6 compact,
  `--group-gap`) of plain lane sits wherever the group changes, so the bus
  colour clearly starts and ends with its group. A click in a gap sets the play
  cursor like anywhere in the lanes (tested).
- **Identity:** the spine (4 px, bus colour, from the bus row through every
  member, ending with a rounded cap at the last member), the band (faint tint,
  **on the bus row only** at rest), and the letter badge (A, B, …, the twin) in
  the bus row, the track's bus picker, the transcript speaker gutter, the
  inspector's bus line, and every mixer-like place (export stems list, music
  report, settings). Speaker hue stays on clips and the track pill; bus colour
  stays in spine, band and badge.
- **Hierarchy:** the bus row is flush with the spine; its tracks are indented
  14 px. The bus fader is filled in the bus colour and labelled "Bus"; track
  sliders stay grey.
- **Expanded:** the bus row (32 px, one line), members below.
- **Collapsed** (chevron, double-click the row, Alt+Mod+← on a member):
  - two or more members: **activity ribbons**: one strip per member (8 px up to
    six members, thinner beyond, never under 3 px; the row capped at 48 px,
    `grammar.js ribbonLayout`, tested) in the member's own speaker hue, filled
    where that track has audible audio, over a faint summed envelope in the bus
    colour. Muted, gated (WP44) and soft-cut stretches use the same hatch and
    dimming as full lanes; candidates and markers are still drawn across the row;
    clip edges are 1 px ticks. A summed waveform would blend the speakers and
    hide who talks when, so it is not used for several members.
  - one member: its summed waveform at 40 px.
  - **Click** in a collapsed row sets the play cursor and selects nothing
    (recommended; Shift+click then selects every member clip in that range).
    **Hover** names the track and clip under the pointer. Double-click the row
    or Alt+Mod+→ expands it.
- **A one-track bus merges into its track (owner decision, 18.10.2026; built).** When a bus has exactly one track
  (Music, Narration), its row is merged into the track's header: the bus badge
  before the role icon, the spine and its cap, no bus row. It saves 32 px per
  such bus (24 compact) and reads as one thing. The bus's level and mute go to
  the inspector's Bus section and to the hover fader. Collapsing it shrinks the
  track to 40 px with its summed waveform. The alternative (a 32 px bus row
  above one track) stays available in `layoutRows(..., {mergeSingle})`; the
  editor merges (`layoutFor`), tested both ways. In the editor the merged header
  carries the badge and, in its level row (current/hover), the track gain and
  a bus-coloured "Bus" fader; that track's pan moves to the inspector's Track
  section (planned; until it exists, unmerging is the way to reach it).
- **Empty bus:** the row alone, name in italics, tertiary; sits last.
- **No bus:** no spine, no band; the track goes straight to the master.
- **The ninth bus:** there are eight bus hues; bus 9 takes hue 1 again.
  Letters and the group gaps keep them apart. Nested buses: section 25.
- **Bus-level things: header or inspector?** The row keeps only what is used
  every minute: collapse, mute, solo (hover) and the gain fader (hover). Pan,
  ducking (depth, attack/release, which tracks duck it), loudness target for the
  stem, output routing and the voice chain belong in the inspector's **Bus**
  section, shown when the bus row (or a merged track's badge) is selected.
- **Assigning:** the track's bus picker (letter + chevron; the menu lists
  "A · Voices", "B · Music", "– · No bus"), or drag a track header onto a
  group: a 2 px insertion line in the bus colour shows where it lands. Both are
  one undoable edit.
- **Bus mute/solo/gain:** M mutes the bus send (a muted bus stays silent under
  solo, WP24.1); **S solos every member as a set** (exclusive, like track solo;
  open question 6 of section 15); gain coalesces drags.

**A typical show** (prototype screen "Typical show"): bus A Voices (Anna's
mic, Anna's backup mic sharing her hue, Ville, a Zoom speech track for
Pekka), bus B Music (one track, merged, with ducking drawn), bus C Narration
(one track, merged, holding two placeholders and a recorded take), gaps between
them. At 1440 × 900 all six tracks fit in comfortable.

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
  is marked in the ruler (hollow triangle).
- **The click rule** (owner, 18.10.2026; `lanes.js pointerIntent`, tested): a
  click **anywhere in the lane area** (a clip, an empty stretch, a bus row, a
  group gap, the space below the last track) sets the play cursor; a click on a
  clip also selects it; **Shift+click only toggles the selection** and never
  moves the cursor. Only the ruler (seek, keep the selection) and the overview
  (move the view) mean something else.
- **Clip selection:** 2 px `--signal-selected`. Its sync partners get the dashed
  scope ring (WP19a), and the other clips **of the same recording** get corner
  brackets (`sibling`, section 18).
- **Range (in/out):** `--selection-range` fill on exactly the lanes the next
  time-shifting edit will touch, accent edges and inward flags in the ruler.
- **Snap feedback** (WP6): a 1 px accent guide while a drag snaps; Mod disables.
- **Undo flash:** section 20.

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

### 8.x Follow is a state, not an action (owner, 21.10.2026)

While playing with Follow on, the view follows the playhead. Any manual view
operation (scrolling, dragging or clicking the overview, a zoom or fit) turns
Follow off; the view then stays where the user put it and the playhead may leave
it. A "Follow" chip in the timeline's bottom-right corner shows the state (on =
accent, off = dim) and toggles it; with Follow off and the playhead out of view,
an arrow at the edge nearest the playhead shows its time. Chip, arrow and the
View command "Show the playhead" scroll there and turn Follow on. Nothing else
re-engages it implicitly: starting or stopping playback does, as do explicit
jumps (below) and a click on the playhead handle or line (about 6 px either side). Never a click near its time, a timer, or the playhead
entering the view by the user's own scrolling. A seek to a spot outside the view
scrolls once only while Follow is on. The rules are in `ui/follow-model.js`; the
state is in the UI store and not saved. Commands: View > Follow playhead
(checked) and Show the playhead; no default keys.

**Every explicit jump re-engages Follow (owner, 21.10.2026).** An explicit jump to
a time X means "take me there": the playhead moves to X, Follow turns on and the
view shows X (scrolling only if X is out of view). Follow is switched off only by
minor adjustments, steering the view while something else happens; a user who
wants to look ahead steers the view. Classification (the table is
`JUMP_SOURCES` in `ui/follow-model.js`, tested in `ui/tests/follow-model.test.js`):

| Action | Class |
|---|---|
| Home, End, In, Out, Back where you left off | jump |
| Next / previous marker | jump |
| Markers panel: a marker row, a drifting clip row, Next / previous drift (F7) | jump |
| Go to time (Spot, double-click on the clock) | jump |
| Transcript: click on a word or a pause marker, a search hit | jump |
| Tab / Shift+Tab to the next stop (word, edge, sound) | jump |
| Candidates panel: selecting a row | jump |
| Inspector Source list: a row | jump |
| Arrow-key nudges of the playhead | seek |
| Click on the ruler or a lane, scrubbing, dragging the playhead | seek |
| Transcript cursor keys (arrows between words) | seek |
| Cursor placed at the splice after a cut | seek |
| Right-click on the timeline (cursor under the pointer) | seek |
| Playhead restored when a project opens | seek |

A seek never changes Follow: a click in a visible spot must not move the view.
History restore and recording jump-to have no time-jump of their own yet; when
they get one it is a jump and goes in this table.

## 9. Keys: what the UI reserves and how it shows them (for WP5)

This section does not define the keymap (WP5 does, from Hindenburg's list); it
fixes how keys are shown and which keys the UI itself needs.

**Reserved by the UI shell:** Space (transport, everywhere except text fields),
Esc (back to the timeline; closes popovers, palette, focus mode), F6 /
Shift+F6 (panels), Mod+K (palette), ? (keyboard sheet), Tab/Shift+Tab (edit
points inside the timeline only), Enter and Backspace (act on the focused
panel's current item: the status bar always says what they will do there),
Alt+Mod+← / Alt+Mod+→ (collapse / expand the current bus), ↑/↓ (current
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
4. (Mostly moot since the owner moved the desktop wrapper, WP15, into the
   first version: in a native window Cmd+T, Cmd+W, F6 and Cmd+L are free.)
   In a browser tab Chrome keeps Cmd/Ctrl+T, +W, +N, +Q and Shift+Mod+T
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
7. Backspace means Delete everywhere since the owner's decision (18.10.2026:
   a soft cut that keeps the gap; X is Cut), but it is also "reject candidate"
   in WP18; Shift+Space means play selection and preview candidate.
   [Acceptable only because they are scoped by focus and the current item; the
   status bar must say which one applies. Recommend renaming WP18's reject to
   K ("keep") so Backspace is always Delete.]
8. F6 in Chrome also cycles the browser's own toolbar focus. [Verify in WP5;
   if the page cannot keep it, add Ctrl+` as the panel key in the browser.]

**New keys from the 18.10 work** (all checked against the WP5 table and the
browser):

| Key | Does | Notes |
|---|---|---|
| Shift+Enter (in a focused slider or numeric field) | default/custom toggle (section 21) | free in WP5; Backspace is not used (it edits text) |
| Alt+Mod+← / Alt+Mod+→ | collapse / expand the current track's bus | WP5 uses Alt+← / Alt+→ for 10 ms playhead steps, so Mod is added; Alt+Mod+arrows are free |
| ` | flip A/B in the Compare bar | the same key as WP24.2; bind by physical key (Backquote = § on a Finnish Mac) |
| 1 – 4 (only while the Compare bar is open) | pick a slot | plain digits are free in WP5; they do nothing outside Compare |
| Mod+J | Spot: jump a clip or the playhead to a typed time | replaces `=` (zoom in), see conflict 1 |

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
| Command bar (palette) | (WP5) `palette.js`; docked over the sidebar column (3.9) | empty, filtered, no results, asking inline | `--shadow-raised`, no scrim | lanes, ruler and playhead stay clickable; focus returns |
| Drop card / overlay | `index.html` `#empty`, `#drop` | empty project, dragging | `--accent`, `--border-strong` | keyboard path: Import button |
| Clip grammar gallery | prototype `screen=gallery` | every signal, both themes | registry | every `SIGNALS` id has a card |
| Theme button | `index.html #theme`, `app.js` | system, light, dark | — | repaints canvases; survives reload |
| Density switch | `index.html #density` (View menu), `app.js applyDensity`, `theme.js densityAttribute` | comfortable, compact | density tokens | `theme.test.js`; lanes and headers follow the tokens |
| View menu | `index.html #view-menu` (native popover) | closed, open | `--toast-*` | Esc and outside click close it |
| Group gap | `lanes.js layoutRows` (gap rows), `tracks.js` `.group-gap` | — | `--group-gap` | `lanes.test.js`: layout and a click in the gap |
| Click rule | `lanes.js pointerIntent`, `app.js onPointerDown` | seek, select, toggle | — | `lanes.test.js` |
| Clip labels | `labels.js`, `timeline.js drawName` | five width tiers, manual name (planned) | `--track-N-label` | `labels.test.js` |
| Siblings | `labels.js siblingsOf`, `timeline.js`, `overview.js` | selection only | `--signal-sibling` | `labels.test.js`; brackets on every clip of the recording |
| Inspector sections | `inspector.js openSections` | open, closed, remembered | `--panel-divider` | `inspector.test.js` |
| Default/custom toggle | `ab-value.js`, `tracks.js toggleable`, `inspector.js` | stored, nothing stored (flash) | `--accent` | `ab-value.test.js`; one undo step per flip |
| Motion setting | `motion.js`, `app.js applyMotion`, `tokens.css [data-motion]` | full, subtle, off | `--dur-*` | `motion.test.js` |
| Crosstalk preview | `crosstalk.js` (built); transcript UI (WP7) | nothing else, also removes | `--signal-collateral*` | `crosstalk.test.js` |
| Collapsed bus ribbons | `grammar.js ribbonLayout`; drawing with WP collapse | 2+ members, 1 member | bus and track hues | `grammar.test.js` |
| Compare bar | prototype `screen=compare` (later WP) | slots, rendering, blind, matched | `--signal-preview` | keys ` and 1–4; Esc discards |
| Import panel and drop preview | prototype `screen=import`, `import-drop` | done, failures, options | `--toast-*`, `--signal-preview` | zero extra clicks by default |

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
row to section 11. Buttons follow `BUTTONS.md` (kinds, sizes, states, order; a
test fails on a button without one of its classes). Labels, fields, help text, check
rows and dialog footers follow `FORMS.md` (one fixed label column, help under the
field, primary last; `ui/tests/form-layout.test.js` fails on a row built the old way).

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

Built in the editor (`ui/`), branch `gui-density` (on top of the merged
`gui-design`):

- tokens in three layers; **two densities** (comfortable roomy default,
  compact unchanged) switched in the View menu and remembered per user;
- progressive disclosure in the track headers, key chips on hover/focus, a
  three-hint status bar and the View menu;
- buses as one-line rows above indented members, a bus-coloured hover fader,
  group gaps and spine caps; `layoutRows` with gaps; one-track buses merged
  into their track's header with the badge and a bus fader (owner decision);
- the click rule (`pointerIntent`), including clicks below the last track;
- collapsible inspector sections (Level and Sync open), remembered;
- informative clip labels by width (`labels.js`), sibling brackets and overview
  ticks for the selected clip's recording;
- the default/custom toggle on track, bus and clip sliders and fields
  (`ab-value.js`);
- the Animation setting (`motion.js`) and toast motion; window-size breakpoints.

Designed and shown in the prototype only (built with their WPs): crosstalk
preview (`crosstalk.js` is built and tested; the transcript UI is WP7), Compare
(WP24.2 and a later engine WP), import of several files with drop preview and
panel, collapsed buses and ribbons, the merged one-track bus, the Source mini
map and sibling list in the inspector, the clip bin grouped by recording, the
docked command bar, sidebar tabs, transcript, history, candidates, focus mode,
gate, soft cut, drift/free/sync badges, placeholders, takes, notes, tether,
labels, the changes view.

Not verified: Windows/Linux, screen readers, real audio (never started), F6 and
Mod+L interception in Chrome, colour-blind users (simulation only), touch
double-tap on a real touch screen.

## 15. Open questions for the owner

From the first design round (still open):

1. Waveform scale for speech: linear or dB-shaped? *Recommended: dB-shaped for
   speech, linear for music.*
2. Spot key: `=` is zoom in. *Recommended: Mod+J.*
3. Finnish keyboard: bind `[ ] `` by physical key? *Recommended: yes.*
4. Mod+F: fade or find? *Recommended: find in the transcript; fade stays G.*
5. Import key in the browser: *Recommended: Mod+I now, Mod+T with WP15.*
6. Bus solo: *Recommended: exclusive solo of all members as a set.*
7. Track order under buses: *Recommended: assigning a bus also moves the track
   in the model to the end of that group.*
8. Role strip: off on the timeline, on in the bin and cards? *Recommended: yes.*

From the density rework (18.10.2026):

9. ~~Merge one-track buses?~~ Decided by the owner (18.10.2026): yes; built.
10. ~~Backspace on overlapping words?~~ Decided: X cuts on all tracks (with the
    collateral preview), Backspace deletes on this speaker only, keeping the gap.
11. **Clicking a collapsed bus:** select nothing, or every member clip in the
    range? *Recommended: nothing; Shift+click selects the members' clips.*
12. **Track inspector section:** the header no longer shows gain and pan at
    rest; should the inspector get a Track/Bus section now (WP4 follow-up)?
    *Recommended: yes, small: gain, pan, bus, voice preset.*
13. **Rename key:** F2 for clips and tracks (Enter is taken by candidates and
    words)? *Recommended: yes.*

From cuts and nested buses (18.10.2026), drawn side by side in the
prototype's "Cuts explained" and "Nested buses" screens:

14. **Auto-Silence in the Cuts list and transcript?** *Recommended: out of
    both; one summary line in the list (24, choice A).*
15. **"Clean up cuts":** *Recommended: palette only (24, choice B).*
16. **Offer one edit's soft cuts to other versions?** *Recommended: a quiet,
    one-by-one offer (24, choice C).*
17. **Lift-cut key:** *Recommended: Alt+X; close gap moves to Alt+Mod+X as
    WP19a has it (24, choice D).*
18. **Nested-bus badges:** decided here as A / A1 / A1a (25); the owner may
    overrule.
19. **Tags:** *Recommended: not now (25).*

From contextual help and onboarding (18.10.2026; sections 26, 27):

20. **Help keys:** decided with the keyboard layer: **F1** opens help (`help.open`),
    "?" stays the keyboard cheat sheet (`help.keys`). F1 needs fn on Mac laptops, so
    the status-bar Help button and Help ▸ Help for this exist too; a user can remap F1.
21. **Follow what I select** on by default? *Recommended: yes.*
22. **The sample project:** who records it (it must be ours to ship)?
    *Recommended: a 3-minute scripted interview recorded for kuulas.*
23. **Tips:** one per 10 minutes at most, after the action. *Recommended: yes.*

## 16. Density and progressive disclosure (owner, 18.10.2026)

The first design was too dense even in its "comfortable" mode. Two densities
remain; **comfortable** (the default) is now roomy and shows less at once;
**compact** keeps the earlier values exactly, for people who want everything
on screen.

| Token | Comfortable (before → now) | Compact (unchanged) |
|---|---|---|
| base text `--text-md` | 13 → **14 px** | 12 px |
| small / extra-small text | 12 / 11 → **13 / 12 px** | 12 / 11 px |
| transcript text / line height | 15 / 1.65 → **17 px / 1.85**, measure 72 → **62 ch** | 14 px / 1.65, 72 ch |
| timecode | 20 → **24 px** | 18 px |
| top bar | 44 → **52 px** | 38 px |
| top-bar buttons | 26 → **40 px visible, 44 px hit target** | 26 px |
| control height `--control-h` | 26 → **32 px** | 22 px |
| header toggles (M, S) `--control-h-sm` | 20 → **28 px** | 18 px |
| status bar | 26 → **32 px** | 22 px |
| track lane `--lane-h` | 56 → **80 px** | 40 px |
| bus row `--bus-h` | 44 → **32 px (one line)** | 24 px |
| group gap | — → **14 px** | 6 px |
| panel padding `--pad-panel` | 12 → **20 px** (≈1.6×) | 12 px |
| row gap `--row-gap` | 4–6 → **10 px** (≈1.7×) | 4 px |
| header column / sidebar | 248 / 320 → **272 / 360 px** | 216 / 280 px |

**Visible controls on the main screen**, counted in Chrome at 1440 × 813 (a
1440 × 900 window): every visible, focusable, hit-testable control.

| | Before (v26.10.17.8) | After |
|---|---|---|
| Prototype, a clip selected (5 tracks, 2 buses before; 6 tracks, 3 buses after) | **61** (60 enabled), 13 key chips | **32** (31 enabled), 4 key chips |
| Prototype at rest (nothing selected, no current track) | — | **24** (23 enabled) |
| Real editor at rest (4 tracks, 3 buses) | **51**, 7 key chips | **22** (20 enabled), 3 key chips |

**Budget: at most 25 visible controls at rest on a typical show** (six tracks,
three buses) in comfortable; chrome costs 11 (Play, Undo, Redo, Import, Export,
Commands; zoom readout toggle, View; four sidebar tabs), each track 2 (M, S),
each bus row 2 (chevron, M). A new resting control must replace one. The
prototype bar shows the live count ("24 controls at rest").

**What moved out of the resting view, and where it went:**

| Removed from rest | Now | Where |
|---|---|---|
| Track gain and pan sliders (2 per track) | current track, hover, focus | inspector Track section (planned) |
| Bus picker chip on every track ("A ▾") | current track, hover, focus | inspector; drag onto a group |
| Bus gain and pan sliders | bus fader inline on hover/focus | inspector Bus section |
| Bus solo | hover/focus | — |
| Key chips beside Play, fields, palette footers | hover and keyboard focus | tooltips, palette, status-bar hints |
| Status-bar zoom −/+, Fit, waveform mode, lane height −/+, follow, theme | — | View menu |
| Five status-bar hints | three, for the focused panel | `?` sheet, palette |
| Speed chip, job chip at rest | only while active | — |
| Inspector Fades, Voice, Source, Details | collapsed with a one-line summary | open on click; remembered |
| Track name as a tab stop | label only (double-click renames) | Enter on the current track (WP5) |
| Bus band behind member lanes, candidate stripes, envelope dots, ducking label | see 5.5 | — |

Compact with progressive disclosure: compact keeps both header rows, the bus
picker and the key chips visible (it exists for people who want everything at
once). Bus faders appear on hover in both densities (a 24 px row has no room
for them at rest).

## 17. Window sizes (owner, 18.10.2026)

No phone layout. Rules, in CSS media queries in the editor and container
queries in the prototype (its "width" control: 1024 / 1280 / 1440 / 1920 / 2560):

| Width | Layout | Comfortable | Compact |
|---|---|---|---|
| **< 1024 × 640** | below the minimum: the page scrolls | — | — |
| **1024 – 1099 (small)** | the transcript moves into the right column above the sidebar (two stacked panes); the status bar keeps only the zoom readout, the view toggle and View; the Commands label hides | lanes 80 | lanes 40 |
| **1100 – 1399 (medium)** | header column and sidebar at their minimums (232 / 280; 180 / 260 compact) | — | — |
| **1400 – 1919 (default)** | as designed (272 / 360) | — | — |
| **≥ 1920 (large)** | the timeline takes the room; the sidebar grows to at most 22 % of the width and stops at 520 px; the transcript measure stays 62 ch (never stretched lines) | — | — |
| **Height < 760** | the transcript dock collapses to its heading (it opens by click or F6); at least three lanes stay visible | — | — |

Checked: the prototype at all five widths in both densities
(`screenshots/width-*.png`); the real editor at 1280 and 1920 in Chrome
(`screenshots/app-1280-light.png`, `app-1920-light.png`, rendered in an
iframe of that size). Not checked on a real 1024 px screen or at 2560 in the
editor.

## 18. Clip labels, recordings, sessions, speakers (owner, 18.10.2026)

### 18.1 Informative clip labels

A clip shows what it is, not just "olli3.wav" (`labels.js`, tested; the editor
draws it today):

| Width of the clip | Label (default template) | Example |
|---|---|---|
| < 48 px | nothing (the file mark only, where shown) | |
| 48 – 99 px | `{person}` | Olli |
| 100 – 169 px | `{person} {take}` | Olli 3 |
| 170 – 399 px | `{person} {take} · {in}–{out}` | Olli 3 · 1:20–3:20 |
| ≥ 400 px | `… · “{words}”` | Olli 3 · 1:20–3:20 · “Mitä ajattelit” |

- `{person}`: the media's person (WP41), else the interview title, else the
  file name; `{take}`: the last number in the file name; `{in}`/`{out}`: the
  source range on the **recording's own clock**, so two clips cut from one file
  read as consecutive (1:20–3:20, 3:20–4:10) or gapped; `{words}`: the first five
  transcript words under the clip; `{file}`, `{interview}`, `{part}` available.
- A label that does not fit steps down a tier; it never overflows. Long file
  names are cut **in the middle, keeping the trailing number whole**
  ("haast…lle_12").
- **Manual name:** a new optional `Clip.name` (empty = auto) overrides the label
  at every width that fits it. Data change (backend task): a field in the
  **edit state** (not material: two edits may name the same clip differently),
  set by an undoable `set_clip` edit, round-tripped in JSON; a `docs/FORMAT.md`
  note. Edited in the inspector's title (click to rename) or with **F2** on a
  selected clip (free in WP5), with "Reset to auto". A name is never identity
  (the content hash is).
- The templates are user settings (WP27/WP35) with the defaults above.

### 18.2 Three relations, three looks, three words

| Relation | UI word (en / fi) | Look | Where |
|---|---|---|---|
| Same file | **recording** / äänite | file zebra tone, file mark chip, **sibling brackets** when one is selected, "Part 2 of 5" | timeline, overview ticks, inspector Source, clip bin |
| Recorded together (sync group) | **recorded together** / äänitetty yhdessä | chain glyph + group number on the selection and partners, dashed partner rings | timeline, inspector Sync |
| Same person | **speaker** / puhuja | the speaker hue | clips, header pill, transcript gutter |

- **Siblings** (`sibling` signal, built): when a clip is selected (or hovered
  with Alt), every other clip of the same recording, on any track, gets corner
  brackets in `--signal-sibling`, and the overview strip gets a tick at each.
  Distinct from sync partners (dashed ring), which are about time, not files.
- **Parts:** when a recording has several clips in the edit, each is "part n of
  m", numbered by source position (`recordingParts`), shown in the inspector
  title and the Source list.
- **Inspector Source section:** a mini map of the whole recording (used in the
  speaker hue, soft-cut in the cut colour, unused grey, this clip outlined) and
  "Other clips from this recording (n)" rows that jump to each.
- **Transcript and clip bin:** the clip bin groups clips under a recording
  header; the transcript keeps time order (reading must not jump) and shows the
  file mark in the speaker gutter when a speaker has more than one recording;
  "Show this recording only" is a transcript filter (planned).

## 19. Crosstalk: what else a cut removes (owner, 18.10.2026)

A transcript cut ripple-deletes the whole stretch its words cover on every
track of the edit scope (WP19a), so overlapping speech of other speakers goes
too. The UI shows that before the key is pressed; no confirmation dialog:
preview plus undo.

1. In the transcript, other speakers' words inside the stretch are marked
   **"will also be removed"**: struck through with a wavy line in
   `--signal-collateral`, on `--signal-collateral-fill`, with a small "×" after
   each (the non-colour twin), even in other paragraphs.
2. The word pop-up shows a one-line summary: "Also removes 2 words from Ville
   and 2.6 s of Pekka (Zoom)", or "Nothing else is removed".
3. The timeline shows the stretch across all affected tracks as a hatched
   `collateral` band with the affected clips outlined (dashed, 2 px), above
   candidates in priority. It breathes softly while words are selected (motion
   "collateral-breathe"; static with animation off).
4. Two actions, by the owner's key decision (18.10.2026: **X is Cut**, ripple
   and onto the clipboard; **Backspace is Delete**, a soft cut that keeps the
   gap): **"Cut on all tracks" (X)** ripples the stretch out of every track of
   the scope, which is exactly what the collateral preview shows; **"Delete on
   Anna only, keep the gap" (Backspace)** mutes just the selected speaker's
   words in place, touches no other track and shifts nothing, so it has no
   collateral at all. The pop-up shows both; the summary line explains the
   difference.
5. **Backend function** (for a cheaper model): `transcript.cut_preview(project,
   word_refs) -> CutPreview` with `range: (start, end)` in project frames,
   `per_track: [{track_id, words: [word_ref…], audio: [(start, end)…],
   speech_seconds}]` for every other track in the scope, and `nothing_else:
   bool`. It is pure, uses `edit_scope` for the tracks, and mirrors
   `ui/crosstalk.js cutPreview` (tested), which the UI can use on the timeline
   words it already has.

The prototype screen "Crosstalk" shows it (both themes, English and Finnish).

## 20. Motion (owner, 18.10.2026)

Gentle cues that pull the eye to what changed. Rules: 120–300 ms mostly, one
animation at a time, nothing loops except real activity (jobs, recording),
animation never moves a target the user is about to click, nothing blocks
input, and nothing animates during playback except the playhead.
`motion.js` (tested) holds the cues; the setting is **Animation: full / subtle /
off** (View menu), default full, and **off when the OS asks for reduced
motion**. It lands on `<html data-motion>`; tokens make every duration 0 for
off and shorter for subtle; "off" shows a static highlight with the same
information.

| Event | What animates | Duration · easing | Subtle | Off (still alternative) | Built |
|---|---|---|---|---|---|
| Undo / redo | the changed clips flash once | 600 ms (`--dur-flash`) · standard | 360 ms, fade | 2 px accent outline for 1.2 s | designed |
| Ripple cut closes its gap | later material slides left instead of jumping | 240 ms (`--dur-slow`) | fade only | undo-flash outline on the moved material | designed |
| Tracks imported | new lanes fade and slide in | 240 ms | fade | accent outline 1.2 s | designed |
| Step to a candidate (] [) | the candidate pulses once | 140–180 ms | 90 ms | 2 px edges + highlighted row | designed |
| Collateral preview | the "also removed" marks breathe softly | 600 ms, while words are selected (stops when deselected) | none | full-strength hatch | prototype |
| A/B flip (Compare) | short cue on the active slot | 140 ms | 90 ms | the active slot filled | prototype |
| Toasts | ease in / out | 140 ms (`--dur-base`) | 90 ms | appear without movement | **built** |
| Soft cut restored | fades back in from its hatch | 240 ms | 140 ms | undo-flash outline | designed |
| Far playhead jump (not playing) | the playhead eases to its new place | 200 ms | jumps | a 1.2 s halo on the cap | designed |
| Default/custom toggle with nothing stored | the field flashes | 600 ms | 360 ms | none (the tooltip explains) | **built** |

Performance: CSS transitions and canvas only, no layout-changing animation
(transform and opacity), one rAF loop; checked with the editor's long-task
monitor (`?dev`) and the Performance panel: no task over 16 ms from a cue.

## 21. Default/custom toggle (owner, 18.10.2026; built)

Double-click a slider or numeric field (double-tap on touch; **Shift+Enter**
when it has keyboard focus) to flip between its default (0 dB, centre, 0 ms)
and the last custom value, for quick A/B listening.

- The remembered value is shown as a 2 px accent tick on the slider track (an
  accent border on a numeric field), and the tooltip says "Double-click or
  Shift+Enter: back to −2.5 dB".
- Each flip is **one** undoable edit with the field's coalesce key, so flipping
  back and forth never piles up history.
- Nothing stored (at the default, never changed): nothing changes; the field
  flashes briefly.
- **Alt+double-click** resets to the default and forgets the custom value.
- Applies to clip gain, pan, fade in, fade out (inspector), track and bus gain
  and pan (headers), and the speed chip (WP26).
- The remembered values are **UI state**: in memory, lost on reload; never in
  the project or history.
- Targets: the comfortable sliders have 18 px thumbs areas inside 28–32 px
  rows; double-tap uses the same handler (browsers synthesise `dblclick`).
- Logic: `ui/ab-value.js` (`toggleValue`, `resetValue`, `createAbStore`;
  tested), wired in `tracks.js` and `inspector.js`.

## 22. Compare: one way to hear options (owner, 18.10.2026; design only)

One concept for every "is this better or that?": a cut vs no cut (the candidate
preview), a value (including the default/custom toggle), track A/B (WP24.2),
alternative takes (WP19e), another edit (WP21), before/after a history step, a
voice preset or FX layer on/off (WP10, WP23), a loudness-matched pair.

1. **The Compare bar** docks at the top of the timeline column (never a modal),
   two lines: slots **A, B** (and **C, D**), each labelled with what it is ("with
   cut", "without", "take 2"), then Keep this one / Discard; under them in small
   text: what is compared, the level match, Blind, the loop, the keys.
2. **One key flips** (`` ` ``) while playing, keeping the playhead position, with
   a 10 ms click-free crossfade; **1–4** pick a slot directly (only while the
   bar is open).
3. **Loop** the compared range: the selection, or the candidate plus 2 s each
   side.
4. **Level match is on by default** (a louder variant always sounds better):
   "B −1.8 dB matched" shows the trim; click it to switch matching off.
5. **Blind** (optional): slots are shuffled and shown as "?" until you pick.
6. **Deciding:** "Keep this one" (Enter) commits that variant as **one** undoable
   step and discards the rest; **Esc** discards the whole comparison and leaves
   the project untouched. Nothing is committed while comparing: the variants
   live in a provisional layer; closing the bar changes nothing.
7. **On the timeline:** the `preview` signal: a dashed top band over the
   compared range in `--signal-preview` with the slot letter in it (twin: the
   letter and the bar), distinct from `provisional` (short dashes on an outline)
   and `candidate` (red stripes).
8. **Offline variants** (dxRevive, voice chain) render first: the slot shows a
   4 px progress bar and "rendering 40 %", and becomes selectable when ready
   ("ready" fills the slot letter).
9. **Only one variant** (e.g. a candidate with no alternative): the bar shows A
   ("as now") and B ("as if cut") automatically; with nothing to compare,
   Compare is not offered (the palette entry is disabled with the reason).

Engine work (playing two variants with a seamless switch, rendering offline
slots) is a later WP. The prototype screen "Compare" shows the bar.

## 23. Importing several files (owner, 18.10.2026; design, backend facts from `Session.import_media`)

**The default needs zero extra clicks:** drop or pick several files and they
arrive as one undoable import, one track per file, in sync (BWF times relative
to the earliest; a file without one starts at 0), mono as speech and stereo as
music; failing files are skipped and named.

1. **After the import**, a small non-blocking panel (bottom left over the lanes,
   like a toast, never a modal) says what was done: "4 files imported as 4
   tracks, in sync", with one-click alternatives: **One after another instead**
   (re-does it as `track_per_file=False`, one undo step), **Undo** (Mod+Z), and
   **Options ▾**.
2. **Drop position matters**, shown before release with ghost clips (dashed) and
   a 2 px insertion line in the accent colour, plus a label of what will happen:
   - onto the empty space below the tracks: new tracks ("4 new tracks, in sync";
     hold Alt for "one after another on one new track");
   - onto a lane: start at the drop time on that track, one after another if
     several;
   - onto the ruler: new tracks starting at that time.
3. **Options** (remembered as defaults, WP35): order **by recording time** (default)
   or by file name; track names **from the interview's person** (default when
   known) or from the file name.
4. **Buses:** "Speech on Voices (A), music on Music (B)" (on by default when those
   buses exist; when they do not, the import creates them only if the user ticks
   it). Existing buses are reused by name; a bus is never created silently.
5. **A dropped folder** (a Zoom or multitrack-recorder folder) imports as one
   group: one track per file, one sync group, one interview.
6. **Failures** are listed in the same panel, one line per file with the reason
   and what was still done ("haastattelu-3.m4a: damaged after 12:40, imported
   the first 12:40").
7. **What the UI sends** beyond today's `POST /api/import {paths, copy_files}`:
   `placement: "tracks" | "sequence"`, `at_frame: int | null` (drop time),
   `track_id: str | null` (drop lane; sequence on that track), `order: "time" |
   "name"`, `track_names: "person" | "file"`, `buses: {"speech": bus_id |
   "create:Voices" | null, "music": …}`, and for a folder `group: true`. The
   answer adds `undo_label` and `alternatives: ["sequence"]`.

Prototype screens: "Import several: drop preview" and "Import several: done".

## 24. Cuts at a glance (owner, 18.10.2026; design)

Prototype screen **"Cuts explained"** (both themes, EN and FI) shows every row
below on one short timeline: Anna and Ville in one sync group, a music bed, and
the selection 4.0–6.0 s over Anna's "niinku öö siis" and Ville's overlapping
"joo", before and after.

| Operation | Key | Timeline after | Transcript after | Cuts list | Clipboard | Message | Undo says |
|---|---|---|---|---|---|---|---|
| **Delete** (soft cut) | Backspace (⌫) | the stretch stays in place, waveform dimmed, soft-cut hatch with red edges; nothing moves | the words struck through in the soft-cut colour | "12:34.0 · 2.0 s · Deleted · gap kept" + **Restore** | untouched | "Deleted 2.0 s on Anna and Ville · gap kept · Restore" | "Undid: delete at 12:34" |
| **Cut** (ripple) | X (Mod+X) | the stretch is gone on every track of the group and on tracks in no group (music); later material moves left; a seam notch where it was | the words gone; a small "✂ 3" marker where they were | "12:34.0 · 2.0 s · Cut · in the clipboard" + **Put back** | the cut audio | "Cut 2.0 s on 3 tracks · in the clipboard · Undo" | "Undid: cut 2.0 s at 12:34" |
| **Lift-cut** | Alt+X (open choice D) | the audio is gone, an empty dashed gap of the same length, nothing moves | a "␣ 2.0 s" marker | "… · Lifted · gap kept · in the clipboard" + **Put back** | the lifted audio | "Lifted 2.0 s · gap kept · in the clipboard · Undo" | "Undid: lift at 12:34" |
| **Mute** | N (Alt+Mod+M) | the selected clip faint and hatched (mute grammar, 5.4) | the clip's words grey and struck through | not listed: a clip state, not a cut | untouched | "Muted 1 clip · Undo" | "Undid: mute clip" |
| **Auto-Silence** | Alt+Mod+P | gate band (dim, waveform flat) where nobody speaks on each track | nothing (silence has no words) | not listed (open choice A) | untouched | "Auto-Silence closed 6 stretches on 2 tracks · Show · Undo" | "Undid: Auto-Silence" |
| **Restore** (a Delete) | Cuts list, palette | the stretch back as it was, outlined once in accent | the words back, outlined | the entry leaves the list | untouched | "Restored 2.0 s · Undo" | "Undid: restore at 12:34" |
| **Put back** (a Cut or lift) | Cuts list, history, or the seam notch's menu | the stretch re-inserted, later material moves right again | the words back, outlined | the entry leaves the list | untouched | "Put back 2.0 s on 3 tracks · Undo" | "Undid: put back at 12:34" |

Rules that hold for every row:

- Only Cut and Lift-cut touch the clipboard; Delete never does (owner,
  18.10.2026).
- Only Cut moves anything. Delete, Lift-cut, Mute and Auto-Silence keep every
  later time where it was, so sync and markers stay put.
- Every row is one undo step; the message's link is the same action as Undo or
  the inverse operation.
- Restore and Put back are separate words because they differ: Restore brings
  back audio that never moved; Put back re-inserts time.

**Open choices** (shown side by side on the screen, the recommendation framed):

- **A · Auto-Silence in the Cuts list and transcript?** Recommended: **out**.
  The Cuts list stays editorial; one quiet line "Gates: 14 stretches · shown
  from the lane menu" says they exist. The transcript shows nothing for gated
  silence. Alternative: one entry per gate and "··· 1.7 s silence" markers in
  the transcript, which floods both with dozens of rows.
- **B · "Clean up cuts"** (make restorable cuts permanent). Recommended:
  **palette only** ("Clean up cuts…", with a confirmation listing what goes).
  Rarely needed and never by accident. Alternative: a button in the Cuts list
  header.
- **C · Offer one edit's soft cuts to other versions?** Recommended: **a quiet
  offer** in the other version's Cuts list ("3 deletes in 'Main edit' cover
  audio used here · Review"), accepted one by one, never applied silently.
  Alternative: nothing, each version is cut on its own.
- **D · The lift-cut key.** Recommended: **Alt+X** for lift-cut, with "close
  gap on all tracks" on **Alt+Mod+X**, which WP19a already names; WP5's key
  list (Alt+X = close gap) changes to match. Alternative: Shift+Mod+X, which
  clashes with WP5's "cut on this track only".

## 25. Nested buses (owner, 18.10.2026; design)

Prototype screens **"Nested buses"** and **"Nested buses: one level
collapsed"**: Speech (A) > Interview 1 (A1: Anna, Ville), Interview 2 (A2:
Zoom: Pekka, Liisa) and Narration (A3, one track, merged); Music (B, one track,
merged). Interview 2 is muted to show the cascade; in the second screen it is
collapsed to ribbons.

**Model change.** One new field: `Bus.parent: str | None` (default `None`).

- A track still belongs to exactly one bus (`Track.bus`), its signal path.
- A bus may have one parent bus: the buses form a forest. Validation refuses a
  cycle, a parent that does not exist, and depth over 3 (top level = 1).
- Routing: a bus's output goes to its parent's input; a top-level bus goes to
  the master. Effective gain multiplies down the chain (dB add).
- Mute cascades down: a muted bus silences its whole subtree. Solo on a bus
  solos its whole subtree; a soloed child keeps its ancestors audible (they
  carry its signal) but not its siblings.
- Ducking, loudness and the voice chain stay per bus; a child's chain runs
  before its parent's.
- Deleting a bus re-parents its children and tracks to its parent (one undo
  step). Old projects load unchanged (`parent` absent = `None`); FORMAT.md
  gains the field.
- Layout (`lanes.js layoutRows`): tree order, depth first; a bus's own tracks
  come before its child buses. A child bus with one track and no children
  merges into that track, as at the top level.

**Look.** The spine/band/badge grammar nests:

- Each bus's own spine is 4 px in its hue; every ancestor continues as a
  **2 px outer rail** to the left of it, so the parent's colour frames the
  whole subtree. Tracks indent one step (10 px) per level.
- The band (faint tint) is on each bus row only, in that bus's hue.
- **Badge style: A, A1, A2 …, and A1a at the third level.** Short enough for
  the 18 px badge and the transcript gutter; it reads as a path without dots.
  Decided against "A.1" (the dot reads as a decimal in FI, "A,1") and against
  a fresh letter per child (loses the parent).
- Gaps: a full group gap between top-level groups, half a gap between sibling
  buses inside a parent.
- Collapse works at every level (chevron, double-click, Alt+Mod+←/→ on the
  focused row). A collapsed bus shows one ribbon per track in its subtree; a
  muted bus's ribbons are dimmed like muted lanes.
- Inherited state is shown, never hidden: a track under a muted bus has a
  dashed M (the existing `.implicit` style) and a hatched lane.

**Hues.** Eight bus hues now (`BUS_HUES = 8`, tokens `--bus-1…8-*`, values in
4.4). 1–4 are the muted originals; 5–8 (sea, iris, ochre, brick) sit at a
different lightness tier so they separate from 1–4 even where the hue is close.
Under deuteranopia bus 2 (olive) and bus 7 (ochre) come close; the letter and
the nesting rails are the twins, as everywhere. A child takes the next unused
hue, not its parent's, so siblings never share a colour; the rail shows the
family.

**Tags (a track in several editing groups): not needed now.** What people want
from tags is already covered: the bus tree (signal and mix), sync groups (what
an edit touches, WP19a), and speakers/interviews (who). A tag would be a second,
overlapping grouping of the same tracks with no visual channel left to show it
without breaking "one channel, one meaning". If a need appears (for example
"all phone guests" across interviews), it is better met by saved selections in
the command palette, which select tracks without becoming a structure.

## 26. Contextual help (owner, 18.10.2026; WP48, v1)

Help knows where you are. **F1** (the command `help.open`, which works
inside a text field too; or Help ▸ Help for this, or the status bar's Help
button) opens the **help panel**: a tab docked in the
sidebar beside the inspector and history, never a modal. The timeline keeps
playing and editing; Space still plays (rule 1). Prototype screens: "Help:
timeline (F1)", "Help: a clip", "Help: a track header + Show me", "Help:
search topics and commands".

Prior art checked: Rhino's F1 opens the topic for the running command, and its
help panel can follow the active command. AppGini docks F1 help at the right
of the window for the focused element. lin-codex (Laravel) keeps help as
Markdown with front matter and one translation per language, falling back when
one is missing. None of them can be embedded in a framework-free ES-module UI.
kuulas takes the three ideas: F1 for the focused thing, a docked panel that
can follow focus, and Markdown topics with front matter. It builds them in
about 300 lines of tested code.

### 26.1 Three layers of words, one source each

| Layer | Where it shows | Source | Length |
|---|---|---|---|
| **Label** | menus, palette rows, buttons, first line of a tooltip | `command.<id>.label` in the locale files | 1–4 words |
| **Hint** | second line of a tooltip, palette row subtitle, the menu's hint line (the hovered item's hint at the foot of an open menu), the status line while a control is hovered | `command.<id>.hint` | one sentence |
| **Topic** | the help panel | `ui/help/<lang>/<id>.md` | 120–300 words |

A tooltip is `Label  [key]` on line one, the hint on line two, and, when a
topic applies to the control, a third line "F1 more help". The status line
keeps its three key hints for the focused panel (section 16). The Help button
sits at the right, before View.

### 26.2 What F1 opens

`help.js helpChain` lists what the user is looking at, most specific first.
`topicFor` takes the first item that has a topic. The chain always ends in
the timeline and then the index, so F1 never shows nothing.

| Focus | Chain starts with | Topic (sample = written now) |
|---|---|---|
| a control with `data-help-id` | that id | the control's topic if one applies, else the next item |
| command palette open | palette | "The command palette" (to write) |
| an error toast or error state | error | the topic for the error (to write; topics may list `errors: [message keys]`) |
| empty project | empty | "Starting a project" (to write) |
| timeline, a clip selected | clip | **A clip** (sample) |
| timeline, a bus row current | bus | **A bus** (sample) |
| timeline, nothing selected | timeline | **The timeline** (sample) |
| a track header | track (bus on a bus row) | **A track** / **A bus** (samples) |
| inspector | inspector, then clip/bus/track | "The inspector" (to write), else the object's topic |
| transcript | transcript | **The transcript** (sample) |
| history | history | **History** (sample) |
| candidates | candidates | "Cut candidates" (to write) |
| a menu-bar item (F1 on it) | its command | the topic that lists that command under `commands`, else the index |
| F1 again inside help | (index) | all topics, with the search field focused |

**Panel behaviour:**
- Focus moves to the topic title, and Esc closes the panel and returns focus to where it was.
- **Follow what I select** (on by default): while the keyboard is outside help, the topic follows the selection and focus. While the keyboard is inside help, the topic stays put.
- **Back** returns along the links followed.
- An untranslated topic shows in English with the line "Not translated yet; shown in English."
- In the app today the sidebar has no tabs yet, so the panel covers the sidebar's other panels while open (`.sidebar[data-help-open]`). With WP47's tabs it becomes the Help tab.

### 26.3 Shortcuts are read from the keymap, so remaps show

- `{key:edit.cut}` in a topic is filled at render time from the live keymap: the entries the user has now (`keymap-config.js resolveKeymap`: `keymap-default.js` with the user's overrides), the same data the cheat sheet, the palette and the menu bar read. `help.js shortcutsFor(command, entries)` is the whole lookup.
- A remapped key therefore shows as remapped (tested).
- A command's other shortcuts are shown with it, primary first: "B ⌘B", "= +". The names come from `keymap-config.js formatCombo`, as in the cheat sheet: ⌘ on a Mac, Ctrl elsewhere, Finnish key names in Finnish.
- An unbound command reads "no shortcut yet". It never shows a guessed key.
- **Modifier variants** (← 1 s, Shift+← 5 s, Alt+← 10 ms) are separate commands with their own entries, labels and keys, so help and the palette list each one and `{key:nav.back_far}` shows Shift+←. The menu bar shows the variant while its modifier is held (`modifiers.js`).

### 26.4 Show me

- `{show:control-id}` renders a "Show me" button. It rings the control carrying `data-help-id="control-id"`: a 3 px accent ring inside its edge, pulsing twice (`--motion` off: a still ring), gone after 2.4 s, scrolled into view.
- Some controls are hidden at rest (track controls, section 16). For those, Show me will first reveal the control (make the track current, open the View menu) and then ring it. That step is planned; today it rings the container.
- A test checks that every `{show:}` target exists in `ui/index.html`.

### 26.5 Search and the index

- The search field searches topics and commands together. Topics are ranked by title (×3), word start (+1) and body (×1), accent-insensitive.
- Commands show their label, keys, hint and a Run button. The help index is therefore also a command list: F1 opens help, and F1 again searches. "?" is the keyboard cheat sheet itself.
- Later (WP5 palette): the command palette also returns topics as "Help: The timeline".

### 26.6 Help content is data

Topics are written so that a cheaper model can add them later: one file per
topic per language.

```
ui/help/index.json          {"topics": ["timeline", "clip", ...]}
ui/help/en/clip.md          English source
ui/help/fi/clip.md          Finnish, same id and structure
```

| Front matter | Meaning |
|---|---|
| `id` | the file name, stable; links use it |
| `title` | the panel title and link text |
| `applies-to` | focus targets (`help.js HELP_TARGETS`): timeline, clip, track, bus, transcript, history, candidates, inspector, palette, empty, error, index |
| `commands` | every command the body mentions (the registry ids) |
| `related` | topic ids for "see also" |

| Body mark | Renders |
|---|---|
| `## Heading`, `- item`, blank-line paragraphs, `**bold**`, `` `code` `` | that, and nothing more |
| `{key:command.id}` | the command's current shortcut(s) |
| `{run:command.id}` | a button labelled with the command's label that runs it |
| `{show:control-id}` | Show me |
| `[[topic]]`, `[[topic\|own words]]` | a link |

Rules for writers:
- Use the second person and the present tense.
- Explain what the thing is, how to use it, and how to undo it.
- Never type a key by hand: use `{key:}`.
- List every command you mention under `commands`.
- Write the Finnish as Finnish, with the same structure, not a word-for-word copy.
- Escape nothing: the renderer escapes all text, so a topic cannot inject markup.

### 26.7 No drift

The tests in `ui/tests/help.test.js` enforce all of these:
- Every ready (registered, not planned) command that has a default key has a label (`cmd.<id>`) and a hint (`cmd.<id>.hint`) in en and fi, and the registry hands out that hint key.
- Every command a topic names is in the registry and has a label and a hint in en and fi.
- No topic names a key by hand: keys come from `{key:}` (a modifier held while clicking is a mouse gesture and is fine).
- `help.open` is in the registry (always available), on F1 in the text-field context, in the Help menu, and so in the palette and the cheat sheet without further work.
- Every topic exists in both languages.
- en and fi carry the same targets, commands, links and Show me controls.
- Every link resolves.
- Every Show me control exists on screen.
- The help panel's own strings exist in both catalogs.

In addition, `tokens.test.js` checks that the prototype embeds the real `help.js`, the topics and the catalog strings.

**The registry contract (met by `commands.js`, `keymap-default.js`):**
- A command is a registry id with `can(state)` and `hintKey`; its keys are an entry in `keymap-default.js` (`labelKey` is `cmd.<id>`), with the user's overrides merged by `resolveKeymap`.
- Help reads only those two: the registry for what exists and what it is called, the entries for its keys. It keeps no table of its own.
- A ready command with no label or hint fails the build.

### 26.8 Built now, and not yet

**Built:**
- `ui/help.js` (pure, tested).
- `ui/help-panel.js` (panel shell: topic, Back, search over topics and commands, Show me, Follow, Esc).
- `help.open` in the registry and on F1 (`keymap-default.js`, text-field context); Help ▸ Help for this; F1 on a focused menu item opens that command's topic.
- The Help button, which shows the key help has now.
- `data-help-id` on the view toggle, the View menu, the track headers and the inspector.
- Six sample topics in en and fi: timeline, clip, track, bus, transcript, history.
- Command labels and hints for every bound or documented command.

**Not yet:**
- Show me revealing hidden controls.
- Tooltips built from label + hint (they still use `title`).
- The menu hint line (needs WP15's menus).
- Palette search of topics.
- Error-state topics.
- The topics marked "to write" above.

On Mac laptops F1 needs the fn key. That is why the Help button and Help ▸ Help for this exist.

## 27. Onboarding (sketch; after v1)

Prototype screen "Welcome (onboarding sketch)". Design only. It reuses the
help panel, topics-as-data and Show me.

1. **First-run welcome.** The only modal in kuulas, and it has a way out on every line:
   - "Open the sample project" (primary): a 3-minute interview with two voices and a music bed, shipped with the app and free to cut;
   - "Start an empty project";
   - "Import audio…";
   - a ticked box "Show me around (2 minutes)".
2. **The tour: real edits, skippable, replayable.**
   - Five steps on the sample: play, select words in the transcript, cut with X, undo, export.
   - Each step is a coach mark anchored to a `data-help-id`. It names the key through `{key:}`, waits for the user's own action (key, mouse or "Do it for me"), and makes one real, undoable edit.
   - "Skip the tour" ends it on any step.
   - "Start the tour" in the Help menu and the palette replays it on a fresh copy of the sample.
3. **Tips, once, on first use.**
   - A small card after the first use of a feature (first cut: "X closed the gap on all 3 tracks. To keep the gap, Backspace deletes in place.").
   - Shown after the action, never before it and never during playback. At most one every 10 minutes, anchored to what was used.
   - "No more tips" turns them off; Help ▸ Reset tips brings them back.
4. **Core-loop checklist.**
   - Import, listen, cut, undo, export. It ticks itself from real events.
   - It sits at the top of the Help tab until done or hidden, and each line has Show me.

**Data:**
- Tour steps and tips are Markdown with front matter, like topics, in `ui/help/tour/` and `ui/help/tips/`: `id`, `trigger` (event), `anchor` (data-help-id), `expect` (command id), and the text in en and fi.
- What has been seen is stored in the user settings (WP35), on this computer only.
