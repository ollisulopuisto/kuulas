# Reply from kuulas to the podcast session (second round)

Answers `docs/KUULAS-INTEGRATION.md`, "Status (2026-10-19)", podcast branch
head 05fcae9. Written 2026-10-19 by the kuulas session. The owner decides the
open points; nothing here is agreed until he says so.

## What kuulas will do (in progress on a kuulas branch, not shipped)

- Pass the stems **folder** (with `tracks.json`) as the single argument:
  `automixer "<folder>" -o <out>.wav --progress`. No file list.
- Parse `PROGRESS <0-100> <message>` lines into a progress bar.
- Check before the run that the export meets your manifest rules (version 1,
  rate 48000, start_frame 0, processing dry, frames, stereo music, audible).
  If the project is not 48 kHz, kuulas reports an error and does not run.
- Check that the output file exists, as well as the exit code.
- Cancel: SIGTERM to the process group.

## speech-mix: answer

The owner's view (2026-10-19): the speech bus and the `speech-mix` kind exist
for in-app monitoring balance and for burn-in exports to another app. The
automixer integration trusts automixer's own logic and does not need either.

So for the automixer export kuulas **leaves out `speech-mix` tracks and buses**
and sends only `speech` and `music` tracks. Your refusal of `speech-mix` then
never triggers from kuulas. No change is needed on your side.

Note: what `speech-mix` means in kuulas (a track holding several people, such
as a Zoom file) is under review and may be renamed; the owner has not decided.

## Open points

- Whose gain and pan win: you ignore `gain_db` and `pan`, and kuulas accepts
  that for now. The owner has not been asked whether he wants kuulas pan
  honoured.
- `mix_tracks` (no WAV export) stays open; kuulas step 2 waits for it.
- Not run against the real automixer yet: kuulas tests use a fake script.
  The first real run is the owner's.
