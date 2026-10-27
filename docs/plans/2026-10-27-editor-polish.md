# October 27 editor fixes

This release adds the owner's start-screen NHSX import, short-term loudness
meter, compact layout and Auto-Silence boundary correction alongside local Orukeet.

## NHSX from the start page

The native source dialog and destination Save dialog run the existing headless
import. The target directory is created exclusively; this action never imports
into an existing project. Cancelling either dialog does nothing. Import failure
keeps any newly created project files, never cleans up recorded media. The new
button is keyboard reachable. The existing File-menu import still targets the
current project. A tiny real NHSX/audio fixture exercises creation and reopening.

## Short-term LUFS

EBU Tech 3341 defines short-term loudness as three seconds:
https://tech.ebu.ch/loudness

The engine offers copied device-output blocks to a bounded deque. A separate
worker uses speechmix.meter.IntegratedMeter; K weighting, power summing and LUFS
conversion stay in the podcast pipeline. The live adapter retains only thirty
100 ms power slots while retaining the shared filter and partial-block state.
It intentionally touches the shared meter's power/speech history to bound memory;
regressions pin that integration. No DSP executes in the audio callback.
Queue gaps, transport sequence changes and device-rate changes reset the window.
Before a full window, the UI shows the 3-second measurement label, not a fabricated
number. The -23 and -16 labels are references, not integrated-program targets or
peak safety thresholds. The peak-clipping latch stays independent and remains
visible until clicked, including while stopped. Existing peak/RMS API fields remain.

## Compact layout

Headers are 260 px, or 240 px on narrower windows, plus the chosen toolbar width.
The mono/stereo detail remains in Inspector. Transcript search shares the heading
row with a 240 px maximum input width; keyboard search and clear behavior stay.
Toolbar actions have raised surfaces, borders, hover and pressed states.
Chrome acceptance measured the former 340 px headers, then confirmed 260/240 px,
heading-row search and visible toolbar buttons at 1600 and 1280 px widths.

## Auto-Silence dotted-edge trim

When an audible opening is shortened, its removed slice must become silent.
Previously it stayed audible in the residual parent, leaving the dotted border
where it was. Add the removed slice to this clip's source-frame silence mask
before materializing the kept opening. Legacy track gates and overlapping clips
retain their scopes. Two regressions first failed against the old code, then
passed by asserting both silence coverage and actual mixed sample output.

Browser acceptance also dragged an actual audible dotted edge left: the server
returned the new explicit opening and a source-scoped silence span beginning
at its new edge. The LUFS DOM test verified the numeric reading, both labels,
and a peak-clip latch that survives Stop and clears when clicked.
