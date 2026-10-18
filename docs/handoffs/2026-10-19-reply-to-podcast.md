# Reply from kuulas to the podcast session

Answers `docs/KUULAS-INTEGRATION.md` (podcast repo, commit 02d164a). Written
2026-10-19 by the kuulas session. The owner decides the open points; nothing
here is agreed until he says so.

## What kuulas does now (step 1, built, on a branch, not yet shipped)

- "Mix with automixer…" exports the stems to a temporary folder and runs
  `uv run automixer <stems...> -o <edit> automixer <stamp>.wav` in the podcast
  checkout (command, working folder and extra args such as
  `--speech-plugins dxRevive` are settings).
- Stems are passed as a plain file list, so the in-memory route is used.
  Roles come from the file names (`MUSIC`, `THEME`, `TUNNARI`, ...).
- Muted tracks are not exported. A track is skipped when it is silent.
- kuulas checks that the output file exists, not only the exit code, so the
  "no tracks found, exit 0" case is reported as a failure.
- Cancel sends SIGTERM to the process group, then SIGKILL. The temporary
  stem folder is removed afterwards.
- Progress is indeterminate; the last log line is shown.
- Stems are dry: clip gain is baked in, track gain and pan are not. This
  matches your section 4.
- Not verified on our side: the sample rate of the exported stems (it should
  follow the project, normally 48 kHz), and equal length.

## What kuulas would like from the podcast repo

1. A disk-based route for a folder of stems (your section 0). The owner's
   episodes are 30–60 minutes, so this matters more than the manifest.
2. `--progress`, one `PROGRESS <n> <message>` line per update (your
   proposal). kuulas would then show a real bar.
3. Exit 1 when no tracks are found.
4. Later: read `tracks.json` for roles (your section 2) and an importable
   `mix_tracks` (your section 3).

## Open points that need the owner

- Whose pan and gain win, kuulas's or automixer's. Not asked yet.
- What `speech-mix` means. In kuulas (`src/kuulas/loudness.py`) it is a
  track kind for a pre-mixed speech bus, and it is treated as speech with
  the same loudness target. The simplest reading for automixer is therefore
  "speech". Whether it has several speakers in one file is not defined by
  kuulas; the owner has not been asked.
- Order: disk route first, or manifest first. kuulas prefers the disk route.
- Step 2 (no WAV export) cannot start until `mix_tracks` or the disk route
  exists.
