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
`rate`, `start_frame` (timeline frame of the first stem sample; always 0 in the automixer's stems, whose folder
route requires it, also for a range preview: Kuulas keeps the range's start in `mix_done.render`) and `frames`, plus per track `id, name, kind,
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

> **Correction (20.10.2026, from the podcast session):** the automixer's real default is
> `BED_UNDER_SPEECH_DB = +1.0` (the loudest 3 s of the bed 1 dB ABOVE the speech; the
> owner's own setting of 2026-10-09), not -1 as written below. The flag is implemented
> (podcast PR #64): `--bed-under-speech-db FLOAT`, -30..+6. Kuulas shows +1 as the default
> and sends the flag only when the value differs from +1.

## Music bed level (request to the podcast session, 2026-10-20)

**Problem (owner, measured by ear):** after an automix export from kuulas the music was "SUPER LOUD" next to the
speech. Cause: `stems_mix.py` sets the loudest 3 s short-term moment of every music bed to
`BED_UNDER_SPEECH_DB = -1.0` below the processed speech level (`change = round(spoken_level + BED_UNDER_SPEECH_DB -
bed_level, 2)`, the `beds:` log line), so beds end up almost as loud as speech. The per-track music gain that kuulas
exports (`gain_db` in `tracks.json`, -27.5 dB in the owner's project) plays no part. There is no CLI switch for the rule.

**Request:** a CLI flag `--bed-under-speech-db FLOAT`, default `-1.0` (= today's behaviour, nothing changes for anyone
who does not pass it), accepted range `-30..+6`. `cli_mix.py` passes it to `stems_mix.mix(bed_under_speech_db=...)`; the
formula uses the parameter instead of the constant; the offset appears in the `beds:` log line so the log shows what
was asked for. Kuulas only shows `beds:` lines it finds, so keep the prefix `beds:`.

Minimal patch, written from reading `apps/automixer/src/automixer/stems_mix.py` and `cli_mix.py` as of 2026-10-20
(hunk line numbers are approximate; kuulas did not apply or test it, the podcast session applies it). Caveat: the
`.nhsx` route (`_mix_session` -> `stems_mix.mix`) is the one with the `beds:` rule in that checkout; I did not find the
`tracks.json` folder route that kuulas calls (`automixer DIR -o OUT --progress`) in that checkout's `cli_mix.py`, so
apply the same change wherever the folder route computes `beds:`, if it is a different place.

```diff
--- a/apps/automixer/src/automixer/stems_mix.py
+++ b/apps/automixer/src/automixer/stems_mix.py
@@ -222,6 +222,7 @@ def mix(
     mic_duck: bool = False,
     mic_duck_db: float | None = None,
     block_level: bool = True,
+    bed_under_speech_db: float = BED_UNDER_SPEECH_DB,
 ) -> stems.StemResult:
     """Miksaa istunnon ``output``iin. Palauttaa ohjelman tason tulokset."""
@@ -385,10 +386,11 @@ def mix(
             spoken_level, _ = _loudness(speech_jobs, stems.anyone_speaking(grid, 0.0))
             _, bed_level = _loudness(music_jobs)
             if spoken_level is not None and bed_level is not None:
-                change = round(spoken_level + BED_UNDER_SPEECH_DB - bed_level, 2)
+                change = round(spoken_level + bed_under_speech_db - bed_level, 2)
                 for job in music_jobs:
                     extra[job["key"]] = extra.get(job["key"], 0.0) + change
                 _log(f"beds: loudest {bed_level:.1f} LUFS, speech {spoken_level:.1f} "
-                     f"→ beds {change:+.1f} dB")
+                     f"→ beds {change:+.1f} dB "
+                     f"(loudest moment {bed_under_speech_db:+.1f} dB under speech)")
--- a/apps/automixer/src/automixer/cli_mix.py
+++ b/apps/automixer/src/automixer/cli_mix.py
@@ -684,6 +684,17 @@ def main():
         help="How far a closed microphone drops, dB (default: the measured -9)",
     )
+    parser.add_argument(
+        "--bed-under-speech-db",
+        type=_bed_db,
+        default=None,
+        metavar="FLOAT",
+        help="How far the loudest 3 s of the music beds sits below the processed "
+        "speech, dB, -30..+6 (default: -1, almost as loud as the speech)",
+    )
@@ -900,6 +911,9 @@ def _mix_session(args, path: str) -> None:
         mic_duck_db=args.mic_duck_db,
         block_level=args.block_level,
+        **({} if args.bed_under_speech_db is None
+           else {"bed_under_speech_db": args.bed_under_speech_db}),
     )
+
+
+def _bed_db(text: str) -> float:
+    """argparse type for ``--bed-under-speech-db``: a finite number in -30..+6."""
+    value = float(text)
+    if not (-30.0 <= value <= 6.0):  # NaN fails too
+        raise argparse.ArgumentTypeError(f"{text}: must be between -30 and 6")
+    return value
```

(`default=None` keeps the default in one place, `BED_UNDER_SPEECH_DB`. `_bed_db` is read when `main()` runs, so it may
sit anywhere at module level; `cli_mix.py` must import `argparse` if it does not already.)

**Test idea** (`apps/automixer/tests`): run the `beds:` step with fixed levels, e.g. speech -20 LUFS, loudest bed
-10 LUFS: default gives `change == -11.0` (`-20 + -1 - -10`), `bed_under_speech_db=-9` gives `-19.0`; i.e. always
`change == round(speech + offset - bed, 2)`. Also: the flag is rejected outside -30..+6 and for `nan`; without the
flag the output is bit-identical to today.

**Kuulas side (built in the same change as this text):**

- Option `bed_under_speech_db` in the Mix dialog, group Music ("Music level under speech (dB)", -30..+6, step 0.5,
  shown default -1). It is stored with the other options and sent only when it differs from -1.
- Before sending, kuulas runs `<automixer command> --help` (timeout 10 s, cached per command, folder and program
  mtime for the session, never fatal) and looks for the text `--bed-under-speech-db`. **So the flag must appear in
  `--help`**, which argparse does by itself.
- Not supported: the flag is not passed, the dialog and the run log/notice warn ("The installed automixer does not
  support this yet; the music stays at its default level"), and the run goes on. `GET /api/settings/automixer` returns
  `capabilities: {bed_under_speech_db: bool}`.

**Later, optional (second step):** `tracks.json` already has `gain_db` per track. The automixer could add the music
track's `gain_db` (relative to a reference, e.g. 0 dB) as an extra offset for that bed, so the fader the user set in
kuulas counts. That changes the meaning of the level and needs the owner's decision; not part of this request.

## Open questions for Olli

1. Frames or seconds for the new manifest fields; the names `muted_frames` / `gate_frames`?
2. Should learned thresholds feed kuulas Auto-Silence, the automixer, or both?
3. How many minutes at the start count as the calibration window, and who defines them (a marker, a region)?
4. Which other podcast-magic features does Olli want in kuulas (item 4d)?

## Speaker balance (owner request 2026-10-20, for the podcast session)

The owner wants the automixer's folder route to do three things, in this order:

1. **Within each speech track:** even out the dynamics (leveler, block levelling). Exists.
2. **Across the speech tracks:** make every speaker the same loudness as the others, measured on
   the speech (while that person speaks), so they are balanced against each other. **Does not
   seem to exist:** from reading `stems_mix.py` / `speechmix` the speakers keep their recorded
   levels (block levelling pulls a block toward that track's own median; `program_trim` only
   trims the SUM to the target). Please confirm, and if so add it (suggested flag
   `--balance-speakers`, with the speaker target derived from the programme target; a
   `--no-balance-speakers` switch so Kuulas can turn it off).
3. **Speech bus against the music bus:** `--bed-under-speech-db` (done, PR #64).

How this meets Kuulas: since v26.10.20.14 the stems carry every track's gain and clip gains, so a
speaker the user pulled down by hand arrives pulled down. When the user has set the balance by
hand (or with Kuulas' Match loudness), Kuulas will send `--no-balance-speakers` ("Done in
Kuulas", same registry as the music level and block levels), so the automixer does not undo it;
when the user has touched nothing, the automixer balances. Needs from the podcast side: the
flag, its log line (for log.txt, like `beds:`), and a word on whether stage 2 already exists in
some form I missed.

**Refinement (owner, 2026-10-20): hand-set levels are approximate, so do not switch the
balancing off; let it measure what the user did and make SMALL corrections.** Replace the on/off
switch with a bounded one: `--balance-speakers-max-db FLOAT` = the most the automixer may move a
speaker's overall level (0 = leave the user's levels alone, large = full automation; suggested
default 6). Optionally `--balance-speakers-tolerance-db` (a dead band: speakers already within
this many dB of each other are left as they are, so a good hand balance is not fiddled with).
Kuulas picks the value: nothing touched = the default (full), levels adjusted by hand = a small
cap (about 2-3 dB), "keep my levels" = 0. The log line should say each speaker's measured level
and the correction applied.

## Live events (owner request 2026-10-21, for the podcast session): `--events`

The owner wants LIVE structured progress while the mix runs, not a JSON report at the end.
Kuulas already reads the automixer's stdout line by line as it is printed, locally and over
ssh (the lines come through ssh live), so no second channel is needed. Protocol:

- New flag `--events` (listed in `--help`, so Kuulas can probe it like the other flags).
  With it the automixer prints, IN ADDITION to every existing text line (unchanged), one
  event per line on stdout: `@@kuulas ` followed by one JSON object on the same line, then a
  newline; flushed at once. Without the flag nothing changes. Older Kuulas versions never pass
  it. Lines that start with `@@kuulas ` are never meant for a human.
- Every object has `"schema": 1` and `"event"`. Events (fields may be added, never renamed):
  - `progress`: `percent` (0-100), `message` (what `PROGRESS` prints now).
  - `track`: `index`, `total`, `name` (a speech track starts).
  - `stage`: `track`, `stage` (read, debleed, plugin, cleanup, measure, dynamics, lag, duck,
    write), `state` (`"start"` or `"done"`, and `"skipped"` when it is switched off). The START
    event is the point: today only the end of a stage is printed, so a slow plug-in stage
    looks like the previous one.
  - `bed`: `loudest_lufs`, `speech_lufs`, `offset_db` (the `beds:` line).
  - `balance`: `track`, `lufs`, `applied_db`, `limit_db` (the `balance:` line, one per speaker).
  - `block`: `track`, `start_s`, `end_s`, `deviation_db`, `gain_db`; `loud`: same with
    `excess_db` (the lines that go to flags.txt).
  - `mastering`: `pass`, `lift_db`, `lufs`, `limiting_lu`; `mastered`: final `lufs`, `lift_db`,
    `limiting_lu`.
  - `warning`: `message`. `done`: `path`.
- Locally and over ssh the same stream works. (A pipe or a file descriptor would not survive
  ssh without extra plumbing; stdout does.)
- Kuulas will parse the lines when present (stage starts drive "now working on", percent and
  track events drive the step text and a time estimate, balance and bed events fill the
  results panel) and keep parsing the old text as a fallback.
