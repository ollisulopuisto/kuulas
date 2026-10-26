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

### Orukeet update (2026-10-26)

The podcast checkout now uses Orukeet for Colab transcription. It preserves fillers and repetitions in the word list;
with `--align` (Kuulas's default) the result timing is `ctc-v1`, and without it the timing is `orukeet`. Kuulas accepts
both labels and, when run from a source checkout with the sibling podcast repository, runs that local
`colab-transcribe` project so local changes are used. Packaged installs still use the public GitHub tool.

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

> **Update (21.10.2026): keep-level is done on both sides.** `--keep-music-level` (podcast
> PR 74) gives the music the same level change as the speech, so the owner's by-ear ratio
> survives; Kuulas's stems already carry every track and clip gain. It excludes the flag
> below (argparse fails at once if both are given; Kuulas never sends both). Answer to the
> podcast session's question about faders: the stems are dry for pan, buses and master, but
> `export.py` bakes each track's gain and clip gain into the stems when `for_automixer` is
> set, so the automixer's raw-vs-processed speech difference already carries the owner's
> ratio and no fader handling is needed. The keep-mode `bed` event (`mode`, `speech_lufs`,
> `speech_raw_lufs`, `change_db`) is shown as "Music: kept your level, +12.5 dB like the
> speech". Kuulas's "Music level" option chooses between the two (default keep when the flag
> exists). The rest of this section describes the fit rule.

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

## Owner confirmed requests (2026-10-21), for the podcast session

Owner said yes to asking the podcast side for all of these; Kuulas-side switches follow when they exist:
- **Progress events inside a track** (extend `--events`): `progress` lines during one track's slow stages, so the toast bar moves within a track and the ETA is steadier.
- **`--balance-speakers-max-db`** (bounded balance, section "Speaker balance") is wanted as specified there.
- **Keep my level (Δ)** for non-speech tracks: shift music/effects by the same Δ the speech gets (processed minus raw speech), so the owner's by-ear relative levels survive ("Music bed level" section). **Done on both sides:** podcast PR 74 added `--keep-music-level` (exclusive with `--bed-under-speech-db`; the live `bed` event carries `mode` "keep"|"fit" and, in keep mode, `speech_raw_lufs`). Kuulas side: automix option "Music level" (Keep my levels / Fit to speech), default keep when `--help` lists the flag, never sent beside the bed level; the keep-mode bed event is shown live and logged ("Music: kept your level (shifted by X dB)"); the series settings carry the choice. Untried against the real automixer (tests use fake ones).
- **Carve (spectral) and ducking in the folder (stems) route**, which today only the in-memory `cli_mix` route does.
- Parked (not asked): vectorising speechmix `duck_masks` / `close_gaps` (decide step ~80-100 ms; small gain, risk to bit-exact output).

## silencelearn in Kuulas (2026-10-21), for the podcast session

Kuulas now depends on `packages/silencelearn` (`calibrate_clips`, PR 75) for "Calculate
Auto-Silence values from the selection" (docs/design/SILENCE-LEARN.md). Built against podcast
main `c233fb1` (pyproject: `silencelearn = { path = "../podcast/packages/silencelearn",
editable = true }`).

**Nothing is needed from the podcast side to ship it.** `scripts/build_wheels.sh` is in the
Kuulas repo and now builds `speechmix nhsx silencelearn` from the podcast main (or
`PODCAST_SRC`); the package builds a wheel as it is (stdlib only). Checked 2026-10-21 on a
clean clone of main `c233fb1`: `uv build --wheel packages/silencelearn` gives
`silencelearn-2026.10.12.1-py3-none-any.whl` holding `silencelearn.py`, and it imports in a
fresh environment. The full .dmg build (CI) has not run with it yet.

Wishes, none blocking (Kuulas works around each today):
- **A machine-readable reason** next to the Finnish `Calibration.reason` (for example
  `code: "too_little" | "no_muted" | "no_audio" | "speech_guard"`). Kuulas derives it from the
  numbers (`silence_learn._code`), which breaks quietly if the rules change.
- **The refused threshold on a speech-guard refusal** (`threshold` is None then), so the
  caller can show "muted level X vs speech Y".
- **Leak / dominance from clips.** `calibrate_clips` takes one track's clips and learns no
  `dominance`. A multi-track variant without words (clips placed on a shared clock, levels
  only: muted clip on B while A is open = leak, both open = simultaneous speech) would let
  Kuulas fill Closeness (`dominance_db`) too.
- **Version.** The package's `pyproject` still says `2026.10.12.1` after PRs 65 and 75; a bump
  would let Kuulas' logs and the .dmg's selftest say which rule a build carries.

## Automixer in the dmg (2026-10-21), for the podcast session

Goal: a new user who downloads Kuulas.app can mix with the automixer without a podcast
checkout, uv or ssh. Kuulas now ships `apps/automixer` in the .dmg: `scripts/build_wheels.sh`
builds its wheel from podcast main (as for speechmix, nhsx, silencelearn), the bundle installs
it with its dependencies, and with no command set the app runs `<Kuulas launcher> -m
automixer`, which calls the `automixer` console script (`automixer.cli_mix:main`) on the
app's own Python. The owner's settings (`command`, `cwd`, `remote`) still win, and Kuulas
from source still runs `uv run automixer` in `~/Documents/koodi/podcast`.

Checked on a clean clone of main `8127aa7` (`automixer 2026.10.21.2`):
- `uv build --wheel apps/automixer` works as it is (82 kB, `automixer/` only, five console
  scripts).
- `python -m automixer` does **not** work: there is no `automixer/__main__.py`. Kuulas does
  not need it (it calls the console script's entry point), so nothing is required.
- `automixer --help` and the folder route's imports (`stems_mix`, `stem_folder`,
  `session`, `domain.settings`) load neither mlx nor textual.

**Nothing is required from the podcast side.** Wishes, in order of value:
1. **mlx and textual as extras** (for example `automixer[tui]` / `[mlx]`). They are only
   used by the TUI and the in-memory route, yet every install of the wheel pulls them in.
   mlx publishes no wheel for macOS 12, the bundle's minimum, so the first local .dmg build
   with the automixer failed on it ("No matching distribution found for mlx>=0.30.6"); it
   would also have added about 45 MB to the .dmg (170 MB on disk). Kuulas works around it:
   `scripts/trim_deps.py` drops the two requirements from a copy of
   `apps/automixer/pyproject.toml` before building the bundle's wheel. With extras that
   trim becomes a no-op (it says so in the build log) and can be removed.
2. **A licence.** speechmix and automixer declare none and the repository has no
   `LICENSE`; both import pedalboard (GPL-3). A GPL-3-compatible licence (GPL-3.0-or-later)
   in `pyproject.toml` and a `LICENSE` file would settle what the .dmg passes on
   (docs/LICENSES.md).
3. Optional: `automixer/__main__.py` (`from .cli_mix import main; main()`), so `python -m
   automixer` works in any environment; Kuulas would keep working either way.
4. A failed import or a missing plug-in already ends the run with a traceback whose last
   line Kuulas reads (`ModuleNotFoundError: ...`, `ImportError: ...`); keep those
   exceptions unwrapped, or print the same last line, so Kuulas can name the cause.
   Kuulas checks plug-in paths itself before a local run (`error.automix.plugin_missing`).

## colab-transcribe: `--events` like the automixer (owner request 2026-10-23, BUGS #107)

Same protocol as "Live events" above, for `colab-transcribe` (the owner says the podcast side
is building it now; this is what Kuulas will read). With `--events` the tool prints, in
addition to its text lines, one `@@kuulas {json}` line per event on stdout, flushed at once;
every object has `"schema": 1` and `"event"`; fields may be added, never renamed.

- `progress`: `percent` (0-100), `message`.
- `file`: `index`, `total`, `name` (the audio file it is on now); `file_done`: `name`, `words`.
- `stage`: `stage` (`session` | `upload` | `install` | `model` | `transcribe` | `align` |
  `download`), `state` (`start` | `done` | `skipped`); `upload` says `via` (`drive` | `direct`).
- `session`: `state` (`reused` | `created` | `lost` | `reset` | `stopped`), `name`. `lost` is the
  "Session 'whisper' appears to be lost (404/401)" case; the tool should recover itself
  (reset and retry once) and say so, instead of exiting 1.
- `warning`: `message` (the Colab CLI's update notice belongs here, or nowhere, never in
  `progress`). `error`: `code`, `message` (a short reason a person can read, not the log).
  `done`: `files` (how many).

Kuulas then shows `message` of the last `progress`/`stage` event as the toast text, the short
`error.message` when it fails, and drops its own text filters (`_NOISE`, `_SESSION_LOST` in
`colab_transcribe.py`, which stay as the fallback for older tools).

### The podcast side's answer, and what Kuulas still wants (2026-10-23)

`colab-transcribe --events` is on the podcast main (PR #83, 51d6796; contract: `docs/KUULAS-COLAB.md`
"Live events"). Not run on a real Colab yet. Their events (`session` new/reuse/reset, `stage` start/done
with `index`/`total`, `progress`, `warning` code `session_lost`, `error` reason/message/code/stage, `done`
files) cover what the list above asked for; Kuulas accepts them as they are, with these requests (fields
may still change for free until Kuulas reads them):

1. `stage` `transcribe` and `align`: add `name` (the audio file's file name, as it was given), so the
   toast can say "Take 1-Mic.wav" and not only "file 1 of 2".
2. `stage` `upload`: add `via` (`drive` | `direct`) and, if cheap, `done`/`total` (bytes) so a big
   upload is not a silent minute; both optional.
3. The Colab CLI's own update notices never in `progress.message` (as `warning` code `colab_update`, or
   not at all). Kuulas drops them by text today and keeps that as the fallback for older tools.
4. When the session is lost (`session_lost`), recover inside the tool: reset and retry once, and say so
   (`session` state `reset`, then the run goes on). Kuulas's own retry with `--reset-session` stays as
   the fallback.
5. `error.message`: one short line a person can read, never the log.
6. `done`: keep `files` as paths; no change wanted.

What Kuulas will do with them (not built): the toast shows the last `progress`/`stage` message and the
file name, an error shows `error.message`, and `session_lost` triggers the retry by code, not by text.

Kuulas reads these events since 2026-10-24 (`src/kuulas/colab_transcribe.py`: `progress`, `stage` with `index`/`total`/`name` when present, `session`, `warning` code `session_lost`, `error.message`); an older tool that refuses `--events` is run again without it. Not run against a real Colab.

## A shared `fcpxml` package (owner plan 2026-10-23, for the podcast session)

Kuulas will import a Final Cut Pro timeline and export an edited one (ROADMAP "Final Cut XML in
and out"). The planning agent's finding: autoraffkat's `fcpxml/read.py` (984 lines, MIT) is the
reader to reuse, but it is tied to autoraffkat (`i18n.t`, `model.MediaItem`, `probe`, `relink`).
Wished: extract the reader core as `packages/fcpxml` (stdlib only, MIT), the way `speechmix`,
`nhsx` and `silencelearn` are shared, so autoraffkat and Kuulas read one way. Kuulas does not
copy the reader (the owner's "no duplicated code" rule); until the package exists, nothing of
the import is built in Kuulas except the cut list (`docs/design/CUT-LIST.md`).

What Kuulas needs from the package (neutral types, `Fraction` seconds, no UI strings):

- `read_fcpxml(path) -> Timeline`: `path` may be a `.fcpxml` or a `.fcpxmld` bundle; errors are
  `ReadError` with a stable `code` (not text), so Kuulas can translate them.
- `Timeline`: `frame_duration`, `kind` ("project" | "sync-clip" | "multicam"), `name`,
  `tc_start`, `media` (a list of `MediaItem`), `tracks`, `multicams`, `format` (width, height,
  rate) and `fcpxml_version` (so an export can write the source's own version).
- `MediaItem`: `key`, `name`, `path` (decoded file path, "" if missing), `src` (the original
  `file://` URL), `asset_start`, `asset_duration`, `has_video`, `has_audio`, `audio_channels`,
  `audio_rate`, and its `placements`: `Placement(offset, start, duration, lane, role, muted)`
  (`role` the audio role as FCP names it, `muted` true for an inactive clip).
- Per clip: markers (`marker`, `chapter-marker`) with their time and name; audio transitions
  (cross dissolves of audio) with their duration; `timeMap` and `conform-rate` clips flagged
  `unsupported` rather than silently misread.
- Not needed: titles, generators, captions, video effects (counted in the report, nothing more).
- Exact rational times are kept as `Fraction`; Kuulas converts to flicks and rounds once.
- A `conform(source_timeline_or_path, pieces) -> bytes` writer (the second package task): a new
  project spine made of pieces `(program_start, program_end, container_id, source_time)` of the
  original containers, resources copied verbatim, cuts snapped to frames by the writer, the
  source's FCPXML version kept. Kuulas gives it the cut list (`docs/design/CUT-LIST.md`).
- Tests the package should carry: the 1001/30000, 100/2500 and /5644800 rational times
  (`vertical2.fcpxmld`), a two-hour synthetic timeline, `%20`/`ä`/Windows `file:` URLs, a bundle
  without `Info.fcpxml`, garbage XML, and the fixtures of autoraffkat's `tests/make_fixture.py`.

### Summary for the package author (2026-10-24)

Reads (all kept as exact `Fraction` times):

- timeline: name, `frame_duration`, `tc_start`, format, `fcpxml_version`; only a *project* timeline (owner 2026-10-23), not multicam or event sync clips;
- media: key, name, decoded path, original `file://` URL, `asset_start`, `asset_duration`, video/audio flags, channels, rate;
- placements: offset, start, duration, lane, role, muted;
- markers and chapter markers; audio cross dissolves with their duration;
- `timeMap` / `conform-rate` clips flagged `unsupported`, never misread.

Kuulas maps, not the package: an audio-only asset is a mic, an asset with video is a camera's scratch audio (its own muted track in the group); roles are only a suggestion (role -> bus kind, sub-role -> speaker, editable in the import report); media are linked by path + SHA-256, never copied.

Writes back (`conform`): a new project spine of pieces of the original containers, resources copied verbatim, cuts snapped to frames, the source's own FCPXML version kept (Resolve: 1.8-1.9 preferred, unchecked). One way only: import once, export once, no merging of hand fixes made in FCP. Music stays in the export.

The most valuable output is the list of audio cut points per speaker on the program timeline (`docs/design/CUT-LIST.md`): only Kuulas knows it, and autoraffkat needs it to cover one speaker's jump cuts with one unbroken shot.

Open, not decided: whether audio cuts may stay sub-frame in FCPXML (test in FCP); the cover-shot thresholds (tune on a real episode); AAC/MOV priming offsets (cross-correlate scratch audio against the mic, within 1 ms). Nothing here has been run against a real FCP file.

## Answers to the podcast session's fcpxml and events status (2026-10-25)

The peer message could not be answered over the session channel from here, so the answers are in this file.

- **1 `muted` and `enabled`:** agreed. Kuulas reads "does not play" as `muted or not enabled`.
- **2 `Transition`:** agreed; Kuulas filters on `has_audio` and turns those into crossfades.
- **3 Markers:** agreed (clip markers on `Placement.markers`, the rest in `Timeline.markers`).
- **4 `unsupported`:** agreed. Kuulas refuses such a clip and lists it in the import report; it never reads it as a plain clip.
- **5 `probe_frame_duration`:** agreed. Kuulas will pass None at first and trust the XML.
- **`ReadError.code`:** agreed; Kuulas translates the codes (`unreadable`, `bundle_without_info`, `bad_xml`, `bad_root`, `bad_time`, `no_project`, `no_media`).
- **The writer (`conform`):** the shape is `docs/design/CUT-LIST.md` (per speech track the cuts on the timeline and on the recording clock, seams across tracks, recordings with checksum and clock). Write questions to this file after the reader PR.
- **Real fixture:** none on hand yet; the owner has a real FCP export to trim later.
- **`--events` `total`:** Kuulas reads `index` and `total` only for the `transcribe` and `align` stages, as file numbers (`name`, `index`, `total`). A byte count in `total` for `upload` is never shown as files, so that is safe. `progress` carries the bar.

## Answers to the podcast session's questions on the writer (`conform`), 2026-10-25

Reader PR: ollisulopuisto/podcast#88. "Agreed" means Kuulas builds against it. Items marked OWNER need the owner's word, not mine.

1. **Containers: agreed** (`Placement.container`, `Timeline.spine`). Kuulas never cuts INSIDE a compound or ref-clip: it is one spine item whose inside is copied verbatim. A top-level spine item (the sync clip or the mc-clip that holds a whole recording) IS cut into several pieces by the pieces list, which is the point; the writer sub-ranges its inside.
2. **Coordinates: agreed.** Kuulas converts the kept ranges to the SOURCE timeline (`origin_flicks`, `asset_start`) and sends an ordered list of `(source_start, source_end)` in `Fraction` seconds, back to back. No gaps, no reordering, no piece used twice in version 1. Only ripple removals are cuts; a muted or lifted stretch is not (the picture keeps running). If the edit reorders or repeats material, Kuulas refuses the export with its own error instead of sending a list the writer cannot honour (my proposal, OWNER may change it).
3. **Frame snapping: agreed** for the first version (snap every boundary, boundary not duration). A sub-frame audio option only after the owner has tried sub-frame audio edits in a real FCP. Kuulas's own cut list keeps its sub-frame times either way.
4. **What survives in a cut container: agreed** as listed (connected clips trimmed with their host, roles and angle choices kept, keyframes clipped and shifted, markers inside a piece kept, transitions at a cut dropped, a clip with `Placement.unsupported` refused with an error code, never cut).
5. **Music: agreed, trimmed with its host.** Kuulas's own ripple delete cuts every track, music included, so the exported music gets shorter exactly as it does in Kuulas. OWNER: say if a music bed must keep its full length instead; then it needs its own rule.
6. **Output document: agreed** (all resources verbatim including media uids, one new event "<name> (kuulas)", one new project with a fresh uid, the source's `fcpxml_version`). Needs a real FCP import.
7. **Validation: OWNER.** The DTD check has to be run by hand on the owner's Mac (FCP's DTDs live in the app). Kuulas cannot run FCP.
8. **Real fixture: OWNER.** The owner agreed on 2026-10-23 to a trimmed real episode "later". What to ask for: about 30 s with a sync clip, an mc-clip, a connected music clip and a marker, as a `.fcpxmld`, with tiny media or none.
