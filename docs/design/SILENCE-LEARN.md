# Auto-Silence values learned from your own muting

Track > Auto > **Calculate Auto-Silence values from the selection** (owner idea, 2026-10-21).
You mute by hand a few stretches you hear as silence, select them together with some clips you
kept, and run the command. The Auto-Silence panel opens with the values learned from them,
says what it learned or why it could not, and previews what it would close. Nothing is
committed until **Accept** (one undo step, as today).

## No duplicated rule

The learning is the shared podcast package `silencelearn` (`packages/silencelearn` in
github.com/ollisulopuisto/podcast, `calibrate_clips`, podcast PRs 65 and 75), the same code
podcast-magic and colab-transcribe use. Kuulas depends on it like on `speechmix` and `nhsx`
(a `../podcast` path source; the .dmg build makes its wheel from the podcast main,
`scripts/build_wheels.sh`). Kuulas only adapts: `src/kuulas/silence_learn.py`.

## The adapter

- **Examples.** The selected clips of *speech* tracks, per track. A muted clip is an example
  of "closed", an unmuted one of "open". Times are the media file's own seconds
  (`offset` to `offset + length`, at the project rate), not the timeline: the package works
  on the file's clock. Clips of music tracks and ids that are gone are not examples.
- **Ungated clips** (the mic stays open under them) keep their role: muted or not is about
  the audio; ungated is a decision about the gate.
- **Levels.** `MediaLevels` answers `level(media, start, end)` with the dBFS of the mean
  square of the channel mean over the window: the same number `analysis.track_levels`
  decides on. From the media's cached envelope (`MediaStore.envelope`, the block analysis
  already uses) when there is one, else from that window's audio alone. Never a whole file
  in memory. A missing linked file has no level (it would read as digital silence) and
  `missing()` says so.
- **Where it runs.** One background job (`POST /api/silence/learn`, kind `silence_learn`):
  the speech is measured first when no measure of it is kept (the same per-track measure the
  panel uses, which is then kept, so the panel opens on it at once), then
  `calibrate_tracks` runs in the analysis worker (offload task `silence_learn`). The
  session lock is held only for the snapshot.

## The mapping to the panel's options

The package learns an **absolute threshold** per track (dBFS over 0.3 s windows: the 90th
percentile of the muted windows plus 1 dB). The Auto-Silence decision is relative: a 20 ms
hop is talk when it is more than `margin_db` (**Sensitivity**) above the track's own noise
floor (`grid.lane`; the floor is the 20th percentile of the track's level with muted clips
left out, `analysis.assemble_measure`). So:

- per track: `margin_db = threshold - floor`;
- one Sensitivity for every mic (the option is one number): the **smallest** learned margin,
  because closing too much is the worse error (silencelearn's own rule);
- clamped to the slider's range (3 to 20 dB); when it was clamped the panel says what was
  learned and what was set.

What the clips cannot teach stays as the panel had it: **Closeness** (`dominance_db`),
the shortest pause and talk, and the padding. `calibrate_clips` learns no leak or dominance
(that needs several tracks at the same moments; see docs/PODCAST-MAGIC.md, "silencelearn in
Kuulas"). The window (0.3 s) and the decision's hop (20 ms) differ; the threshold is a taste
value in the package, and the live preview is where the owner checks it.

On white-noise test material the learned margin is about 1 dB, so it is clamped to 3 dB: the
muted noise's 90th percentile is barely above its own 20th. Real rooms with bleed in the muted
stretches give more. Not yet seen on a real session.

## Refusals are explained

Each track's answer has a code the UI translates (`ui.silence.learn_<code>`, en and fi). The
package's own `reason` is Finnish prose for its log; Kuulas logs it (`log.silence.learn`)
and derives the code from the numbers:

| code | when |
|---|---|
| `learned` | a threshold; the panel also says the share of the kept clips' windows above it (`kept_share`), or that no kept clip was selected so the speech check did not run |
| `too_little` | under `MIN_SECONDS` (3 s) muted |
| `no_muted` | no muted clip of that track selected |
| `no_audio` | the media is missing |
| `speech_guard` | the muted level is within `GUARD_DB` of the kept clips' speech level: was speech muted? |
| `not_measured` | the track is muted, so Auto-Silence does not measure it (no floor) |

A selection with no clip on a speech track is refused at once (`error.silence.learn_no_selection`).
When nothing was learned the panel keeps its values and says so.

## Series

Nothing new: Accept remembers the options for the project (`state.autoSilence`), and a series
already stores the Auto-Silence options (docs/design/SERIES.md), so "Save as series defaults"
carries the learned values to the next episode.
