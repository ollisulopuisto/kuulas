# The running automix toast

Design review, 21.10.2026. Status: **built** (structured toast, fallback to the old line).
Mock: [`toast-mock.html`](toast-mock.html) (open it from the checkout; Light / Dark buttons,
"Animate the tracks phase" walks the nine stages so you can see nothing jumps).

Owner: "okay format the toast design better then".

## 1. The problem

The toast was one sentence: `The automixer is mixing… 49 %: 3/4 track 1/4 Olli: plugin (3/9) … ·
about 12 min left`. Five facts in one string, wrapping wherever the track name ended, and
every poll (500 ms) re-flowed it. The data behind it was always structured (`StepTracker`
knows phase, track, stage); only the UI got a string.

**At a glance the toast must say:** is it still working, how far (percent), how long
(time left), where (phase n of 4 or 6), and in the long tracks phase which track of N and
which of the nine stages, working or done. Then: how to stop it, how to see why.

## 2. Layout: one hierarchy, four rows, fixed height

```
┃ Mixing with the automixer           about 12 min left  49 %   ×
┃ ███████████████████▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
┃ Processing tracks                                Step 3 of 4
┃ Track 1 of 4  Olli                   plug-in 3/9  ■■▮□□□□–□
┃                                        [ Cancel ] [ Show log ]
```

- **Title row:** what runs (bold), then time left (secondary) and percent (bold, tabular)
  on the right. The eye goes title → number; the number never moves.
- **Bar:** full width, 4 px, the job's whole progress. One bar, one number.
- **Phase line:** phase name (medium weight), "Step n of N" right-aligned.
- **Detail line:** in the tracks phase "Track i of n", the name (ellipsised, full name in
  the tooltip), the stage text and "3/9", then nine **pips** pinned to the right edge (they
  never shift). Outside the tracks phase this line is the tool's last line, without its
  "3/4" prefix (it is said once, above).
- **Buttons:** Cancel and Show log bottom right, × top right (the toast head's last item,
  BUTTONS.md). Secondary buttons as before.
- Width fixed at 480 px (narrower windows: the viewport minus 16 px each side); both detail
  lines always reserved and `nowrap`. **Nothing changes height or width while the stage
  changes.**

Pips are shape-coded, not colour-coded: done = filled, working = filled and 1.6× taller,
pending = hollow, skipped (stage switched off, or reported skipped) = a dash. The stage is
also text beside them ("de-bleed done", "duck skipped").

### (a) Stems (step 1 of 4)

```
┃ Mixing with the automixer                              18 %   ×
┃ ███████▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
┃ Preparing stems                                  Step 1 of 4
┃ Maija 2/4
```

Analysis before the tool's first PROGRESS: no percent, the bar stays where the stems left
it and shimmers (opacity only). No time left yet: the estimate only comes from the
automixer's own numbers.

### (b) Tracks with a stage: the wireframe in section 2

### (c) Mastering (4 of 4)

```
┃ Mixing with the automixer           under a minute left  93 %  ×
┃ ███████████████████████████████████████████████████████▒▒▒▒
┃ Mastering                                        Step 4 of 4
┃ Engine: master
```

### (d) Another Mac (6 phases)

```
┃ Mixing with the automixer                              19 %   ×
┃ ███████▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
┃ Uploading                                        Step 2 of 6
┃ Olli.wav
```

Downloading is "Step 6 of 6" with the file rsync names. The host is not repeated: the Mix
dialog said it, and the title row has no room to spare.

### (e) Narrow (phone-width web view, small window; below 520 px)

```
┃ Mixing with the aut…  about 12 min left  49 %  ×
┃ █████████████▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
┃ Processing tracks                Step 3 of 4
┃ Track 1 of 4  Olli               plug-in 3/9
┃                     [ Cancel ] [ Show log ]
```

The pips go; the stage text and its count stay. The title ellipsises before the numbers do.

### (f) Finished, failed, cancelled: unchanged

The plain one-line notice as before (path and summary, Show in Finder / Show log; the error
and its Show log). They are read once and kept; the structure is for something that changes.

Paused while playing: "Paused while playing" takes the time-left slot; the rest stays.

## 3. What I cut

- **"The automixer is mixing…"** as a sentence: the title says it once, without the ellipsis.
- **The step prefix "3/4" in front of every line**: it has its own place now.
- **"done (2/9), now plugin"**: the pips show what is done and what is next; the text keeps
  only the current stage.
- **The stems' own 0-100 % sub-percent** ("Writing the stems… 45 %"): one number, the whole
  job's, which only grows. 100 % is never shown while it still runs (capped at 99).
- **The host name, the track count in the title, an animated working pip**: noise, or a
  second animation (GUI-DESIGN.md §20: one at a time).

## 4. Data and fallback

The job lists `detail` (null by default and after the job ends), set by
`automix.run` through `_Progress.set_detail` every time `StepTracker` builds a line:
`{phase, phases, phase_name, track: {index, total, name} | null, stage: {name, n, of,
state: working | done | skipped, off: [stages switched off]} | null}`. `message` stays exactly
as it was. `ui/automix-toast-model.js` turns `(job, t)` into the view; without a usable
`detail` (older server, a job that is not running) it returns `rich: false` and the toast is
the old line.

## 5. Accessibility and motion

- The bar is `role="progressbar"` with `aria-valuenow` (absent while indeterminate) and
  `aria-valuetext` "49 %, about 12 min left".
- The notice's own `aria-live` is switched off while the rich toast shows; a separate polite
  region (`#notice-live`) says only the phase ("Processing tracks, Step 3 of 4"). A stage
  change every few seconds is not announced; a phase change is. Done and errors are
  announced as before.
- Text, not colour alone: every pip state has its own shape, and the stage is written out.
- Motion: the bar fill moves by `transform: scaleX` (no width animation), 240 ms; the
  indeterminate shimmer is opacity. Both stop under `prefers-reduced-motion` and the
  Animation setting "off".
