# podcast-magic and kuulas: how mutes exist here, and what the contract could be

Written 2026-10-19 for the podcast-repo session (answers to its five questions). "Verified" means read in the
kuulas code on `main` that day; "assumed" means a proposal or a guess. kuulas cannot import the podcast Python
workspace: the contract is files plus command lines, as with `automixer` and `colab-transcribe`.

## 1. How a mute exists in a kuulas session (verified)

Three separate things, all part of the edit state (stored whole in the project's SQLite history, so undo keeps
them); every position is an **integer frame at the project rate** (`Project.rate`, normally 48000), counted on the
**timeline** (frame 0 = the start of the timeline); a clip also has `offset` = the source frame at its start.
Seconds are not stored. Flicks only appear for the recording clock of a media file (`time_ref_flicks`).

- **Clip mute** (`Clip.muted`, bool): the soft cut. `ops.mute_range` / `ops.mute_ranges` split the track's clips at the
  range edges and mute the pieces inside, so a hand-made muted stretch is a run of muted clips (same media, contiguous
  source). Muted clips stay visible and unmute exactly. This is what a user does by hand with I/O and Backspace.
- **Track mute and solo** (`Track.mute`, `Track.solo`): whole-track switches.
- **Gate** (`Track.gate`, tuple of closed `(start, end)` frame ranges, sorted, non-overlapping): the result of
  Auto-Silence (WP44), machine-made. Silent whatever the clips say.

## 2. What stem export does with them (verified)

`mixer.track_stem` renders muted clips and gated ranges as **exact digital silence**, with a 30 ms ramp on the open
neighbour (the ramp is inside the open stretch). A muted track, or a track not soloed while another is, becomes an
all-zero stem and `"audible": false` in `tracks.json`. Pan, buses and master are not applied. `tracks.json` v1 has
`rate`, `start_frame` (timeline frame of the first stem sample) and `frames`, plus per track `id, name, kind,
speaker, channels, file, audible, gain_db, pan`. Muted ranges are listed by the two optional fields below.

**Built (WP85 step 1, `stem_ranges.py`):** two optional per-track fields on the stem's own clock (frame 0 = the stem's first
sample, i.e. timeline frame minus `start_frame`), in frames, so no rounding; the consumer divides by the manifest's `rate`:

- `"muted_frames": [[start, end], ...]` = hand-made clip mutes, merged, `end` exclusive;
- `"gate_frames": [[start, end], ...]` = Auto-Silence gate ranges.

Both are integer frames, sorted, merged (touching ranges are one), clipped to the exported range `[0, frames)`, so a
range or selection export counts from its own first sample. A field is left out when its list is empty, and for a
track that is not audible neither is written (the whole stem is silence, `audible: false`). `version` is unchanged:
older readers ignore the fields. The same fields are written for the automixer route.

They are kept apart on purpose: learning a silence threshold should use the **hand-made** mutes only, never the
machine-made gate (that would learn from its own output). Names and unit are open for Olli (frames vs seconds).

## 3. Is "mute the quiet stretches in the first minutes" natural here? (assumed)

A user can do it today (mark with I/O, Backspace), and it is natural, but it is invisible as an intention. I would offer it
explicitly: a command "Learn silence from the muted parts" (Track > Auto), which exports the stems and manifest, runs
the external tool, and stores the result per track (silence threshold, leak/dominance margin) as settings that
Auto-Silence and the automixer call can use. kuulas would call a command line and read a JSON file back, e.g.
`podcast-magic calibrate --tracks tracks.json --stems DIR -o silence.json` (file name and schema for you to define).

## 4. Other features kuulas wants, and the interface

- (a) **Transcription with corrected word starts: already wired** (`colab-transcribe --audio F --json DIR --progress [--align]`,
  WP78); kuulas reads `<stem>.words.json`.
- (b) **Auto-Silence: in kuulas it is a gate (non-destructive, merged ranges), not a cut.** If learned thresholds beat the
  built-in speechmix grid, kuulas wants them as an input file per track, not a different way of muting.
- (c) Transcript exports (txt, md, srt, vtt, speaker script) exist in kuulas already. A downmix transcript: not wanted.
- (d) Open for Olli.

## 5. What should not be carried over (assumed)

Anything that rewrites the project (kuulas owns the project file; external tools only produce files), Hindenburg `.nhsx`
specifics, Google Drive routes for private audio (audio goes straight to the VM, never via Drive), and anything that needs
importing the Python workspace.

## Open questions for Olli

1. Frames or seconds for the new manifest fields; the names `muted_frames` / `gate_frames`?
2. Should learned thresholds feed kuulas Auto-Silence, the automixer, or both?
3. How many minutes at the start count as the calibration window, and who defines them (a marker, a region)?
4. Which other podcast-magic features does Olli want in kuulas (item 4d)?
