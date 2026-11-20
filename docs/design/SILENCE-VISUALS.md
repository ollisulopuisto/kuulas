# Silent states on the timeline

Owner decisions, 2026-10-21. Supersedes the "Look" row of GUI-DESIGN.md 5.4 (mute, gate
and soft cut). Amended 2026-11-20: the outline-only wave and the stripes are gone; a silent
stretch is now a much darker clip body carrying the same filled half-shape heavily dimmed
(the "ghost"), and a fully silenced (muted) clip drops the clip's upper border. Code:
`ui/silence-visuals.js` (pure), `ui/paint.js` (waveform layer), `ui/timeline.js` (overlay).
Mock: [`silence-visuals-mock.html`](silence-visuals-mock.html).

## The problem

A muted clip (`Clip.muted`, the user's decision) and a stretch closed by Auto-Silence
(`Track.gate`, computed per track, across clips) looked the same: both were crosshatched.
The hatch also covered the clip borders, so the owner could not see where to grab the edge of
a gated clip. A clip can be partly gated and partly not; that was hard to read too.

## The language

Independent channels, each with one meaning, so they combine without confusion:

```
 state                         | waveform        | body          | icon              | lane
-------------------------------+-----------------+---------------+-------------------+------------------
 sounds                        | FILLED          | normal        | -                 | normal
 muted clip (you)              | DIMMED FILL     | much darker   | -                 | no upper border
 closed by Auto-Silence        | DIMMED FILL     | much darker   | LOCK (amber)      | dashed amber ends
 muted AND gated               | DIMMED FILL     | much darker   | LOCK              | dashed amber ends
 keeps the mic open (ungated)  | FILLED          | normal        | OPEN LOCK (green) | normal
 Auto-Silence preview          | OUTLINE in teal | normal        | "preview" label   | dashed teal edges
 not part of the operation     | (as above)      | (as above)    | (as above)        | GREY and/or DIM
 media file missing            | NONE            | red fill      | WARNING sign      | red 2 px edge
 clips in one group            | (as above)      | (as above)    | group badge       | one rounded outline
```

Legend:

- **Filled** waveform = it sounds. **Dimmed fill** (the same filled half-shape at 35 %
  strength, `SILENT_WAVE_ALPHA`) on a much darker body = silent (owner, 2026-11-20). The
  ghost of the audio stays, so you can still judge what is cut, and the strong darkening
  reads as silent at any zoom. Nothing is striped or outlined.
- **Lock** = closed by Auto-Silence; **dashed amber lines** mark where the closed stretch
  starts and ends, so it reads as its own piece. They are not clip edges: thinner, dashed,
  amber, no handles, not draggable. **Open lock** = released from it: the clip keeps the
  mic open (`Clip.ungated`). A muted clip and a gated stretch differ only by the lock (and
  its dashed ends).
- **Thin rounded outline** round several clips = one group (`Clip.group`, Edit > Group).
- **Dim / grey** = not part of what you are doing now (range scope; listening to a rendered
  mix). Never used for silence.
- **Teal outline with dashed edges** = what the Auto-Silence preview would close.
- **Nothing is hatched.** The owner found the hatch "almost too aggressive". The diagonal
  hatch stays only for cut candidates, collateral and edge-drag regions.

A clip half inside a gate is filled where it sounds and a dimmed ghost on the darker body
where it is silenced, with the lock at the left of the visible part of the closed stretch.

## Rules

- **One ghost strength** (owner, 2026-11-20): muted clips and gate-closed stretches share the
  same dimmed fill (`SILENT_WAVE_ALPHA`, 35 %). The much darker body is the silence signal;
  the ghost is decoration, so its contrast is not WCAG-bound. A muted clip also drops the
  clip's upper border: the sides and bottom keep the edge findable, the open top is one more
  "this is silenced" cue.

- **Borders on top.** Clip borders, handles, the selection outline, fade and gain handles are
  drawn after every silent-state overlay (`TRACK_LAYERS`, tested). The outline and the body
  tone are on the waveform canvas under the whole overlay. The preview's dashed edges stand
  2 px inside the body, so a border never hides them.
- **Clip border** (owner, 2026-10-24): solid 1 px neutral `--signal-clip-edge`, independent
  of the speaker hue: `--p-gray-25` in light, `--p-gray-48` in dark. It is darker than every
  filled waveform; in dark mode it sits between the bright wave and dark body. Tests require
  border/wave >= 1.6:1 and border/body >= 1.5:1 for all seven hues and both file zebra tones.
  These adjacent-graphic separation floors supplement the existing >= 3:1 waveform/body
  checks; they are not a claim of 3:1 border/wave accessibility. Selection keeps its 2 px
  outline, gate ends their dashed amber strokes, and groups their outer rounded outline.
  Muted waveform outlines and padlocks are unchanged.
- **The lock** sits 3 px in from the left of the *visible* part of each closed stretch, just
  under the name strip (and the words row when shown, `lockTop`; owner 2026-10-23: a long clip
  name had covered it), on a small chip of `--surface-panel`. It slides right past clip edge
  zones (6 px) and fade handles; a stretch with no room left gets no lock and the
  outline alone says silent (`lockSpots`, tested). Hover: "Mic closed by Auto-Silence.
  Double-click to open this stretch."
- **The open lock** follows the clip name, before the right edge zone and badges
  (`openLockSpot`). Hover: "This clip keeps the mic open: Auto-Silence never closes it."
- **Toned body**: `--signal-silent-body`. First a light darkening (6 % light, 20 % dark);
  the owner found it too close to the open body (v26.10.20.35), then 22 % (light) and 60 %
  (dark). On 2026-11-20 the owner asked for real contrast: now 35 % (light) and 75 % (dark),
  a step of at least 1.5:1 (light) and 1.2:1 (dark; WCAG ratios compress dark colours, the
  change is plainly visible) and never crushing past 3.5:1. The body carries the silence
  signal alone; the dimmed ghost wave on it is decorative.
- **Stretch ends** (`stretchEdges`, tested): a 1 px line dashed 3/3 in `--signal-gate-lock` on
  the first and last pixel of each closed stretch, drawn under the clip chrome. An end the view
  cuts off is not drawn (the stretch goes on); an end within 2 px of a real clip edge is left to
  the real border; a stretch under 4 px wide gets none. Not hit-tested: a drag there paints a
  range or moves the clip as anywhere else.
- **Groups** (`groupOutlines`, tested): one 1 px rounded outline in `--signal-group`, 1.5 px
  outside the bodies of all members (across tracks), drawn after all lanes. Different from the
  selection (2 px, on the clip's own border, near-black/white) and from the dashed amber
  stretch ends. Members on a collapsed track do not count. Sync partners (recordings in sync,
  not an explicit group) keep their corner brackets on selection; they get no outline.
- **Missing media** is not silence: no waveform at all (not even an outline), the
  `--signal-damaged-fill` body, a 2 px `--signal-damaged` edge, a large warning triangle and
  "File missing". Double-click opens File > Locate media. Clip > Locate / Relink media…
  (always in the clip's context menu) accepts an edited copy with another checksum, after a
  confirmation that shows both lengths; one undo step; neither file is changed.

## Inactive lanes: dim, desaturate or both

A view preference (View > Lanes outside the operation; remembered per user):

| Variant | Lane | Waveform | Header |
|---|---|---|---|
| **Grey and dimmed** (default) | grey palette + veil at 0.30 | readable | grey, 70 % |
| Grey | grey palette, no veil | as readable as active | grey |
| Dimmed | veil at 0.72 (the old look) | faint | 35 % |

Why the default is both: desaturating keeps the waveform readable (the grey of the same
relative luminance keeps every WCAG contrast ratio, tested), while the hue loss says "not in
play"; a light veil adds the step back that grey alone lacks next to low-chroma hues (music's
sand, the grey lanes). Cost: none per frame. The grey palette is computed once per theme
(`desaturatePalette`, `theme.paletteInactive`); headers use a static CSS `grayscale` filter.
It combines with silence without confusion: a silent clip in an inactive lane is a grey
outline.

## Accessibility

Never colour alone: the much darker body vs the plain one, lock vs open lock vs none, dashed
vs solid and the "preview" word are shapes. Reduced motion: nothing here moves. Contrast (WCAG 1.4.11, 3:1
for graphics; `ui/tests/silence-tokens.test.js` checks the silent-state pairs and
`ui/tests/tokens.test.js` checks border separation in both themes):

| Pair | Light | Dark |
|---|---|---|
| clip border / filled waveform (worst hue) | >= 1.75 | >= 2.00 |
| clip border / body, including alternate file tone (worst hue) | >= 12.13 | >= 1.97 |
| body vs toned body (the step) | >= 1.58 | >= 1.21 |
| lock / stretch ends on its chip (`--surface-panel`) | 6.26 | 10.42 |
| lock / stretch ends on any body / toned body (worst) | 7.16 / 4.54 | 7.65 / 11.06 |
| open lock on its chip | 7.74 | 8.35 |
| open lock on any body / toned body (worst) | 8.85 / 5.61 | 6.13 / 8.86 |
| group outline on the lane / any body (worst) | 9.77 / 10.32 | 8.53 / 6.02 |
| preview teal on the lane | 4.36 | 8.76 |
| missing sign on its fill | >= 3 (tested) | >= 3 (tested) |

On a *filled* waveform the icons would fall to about 1:1 against some hues (amber lock on
amber wave), which is why they always sit on the panel chip. Tokens: light lock
`--p-amber-40`, open `--p-green-34`, group `--p-gray-30-b`, silent body `--p-gray-22-a35`;
dark lock `--p-amber-84`, open `--p-green-76`, group `--p-gray-76`, silent body
`--p-black-a75`. The lock is
warm ("the machine did something here"), the open lock green ("you released it"), the
preview teal; three different colours, tested, and three different shapes.

## Edge drags inside a gate

The owner reported that the borders of a gated clip "cannot be dragged". `hitTest` reports
the clip edge and the gate together, and the press starts an edge drag before the gate is
consulted; `dragIntent` and `tweakZone` stand back on an edge (`ui/tests/gate-edge-drag.test.js`).
No code path took the press. The cause was visual: the hatch covered the borders, and the
gate's own edge ticks, which looked like grab handles, are not draggable (a gate boundary is
not an edit handle). Both are gone.

## Not verified

The look in the real window at several zoom levels and lane heights; the outline's cost on a
45-minute zoomed-out view (two points per pixel column, one path per run; not measured);
whether the lock should also mark stretches shorter than the icon.

## Sync drift marks

Sync drift and free-from-sync marks are hidden by default because deliberate offsets can be normal
in a session. View > Options > Show sync drift opts in to a low-alpha label tint and a compact dot
(drifting) or unlinked-rings icon (free). The mark carries no number; hovering keeps the exact
offset and anchor in the tooltip. The Markers list and Next/Previous drifting clip navigation do
not depend on this display preference.
