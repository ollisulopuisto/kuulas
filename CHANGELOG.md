# Changelog

## [v26.10.16.4] - 2026-10-16

- Error messages are in Finnish as well as English. kuulas follows the
  language of the computer (Finnish if it is set to Finnish, English
  otherwise). Edits that cannot be made, missing media, and transcription
  that needs an install all say what went wrong in that language.
- Messages from the speech pipeline (plug-ins, mastering, bleed removal) are
  in Finnish too.
- The app's own screens are still English until the interface is translated.

## [v26.10.16.3] - 2026-10-16

- Analysis of several speech tracks (what decides who is talking, for
  Auto-Silence and automixing) now runs one track per processor core. The
  result is the same as before, only faster on a multi-track project.

## [v26.10.16.2] - 2026-10-16

- Solo now works the way a mixing desk does: soloing a track hears it even
  when it is muted, and soloing another track unsolos the first. Hold the
  additive modifier to solo more than one track. A muted bus still silences
  its tracks, even when they are soloed.

## [v26.10.16.1] - 2026-10-16

First working core of kuulas. There is no app to open yet; this release is the
engine the app will be built on.

- Projects of tracks, clips, buses and a master, changed only through named
  edits: move, trim, split, ripple delete with crossfades, mute, fades, gain
  and pan, automation, sync groups, and selection-wide edits.
- Every edit is saved to disk before it counts, and undo keeps every branch,
  so nothing is lost after a crash or an undo.
- Import of audio files and video (audio track only), kept as lossless FLAC
  where the source allows it, with files identified by content, so renamed or
  moved files are recognised.
- Auto-Silence and automixing, using the podcast pipeline's speech detection.
- Transcript words that follow the audio, and cutting audio by deleting words.
