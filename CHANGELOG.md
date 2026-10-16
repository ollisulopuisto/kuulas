# Changelog

## [v26.10.16.6] - 2026-10-16

- Sync groups now belong to the recordings, not to clips: marking clips in
  sync puts their whole files in the group, every edit of the project sees
  the same groups, and marking or unmarking undoes like any edit. Resync
  works as before.
- Recording times (transcript words, recorder start times, sync offsets)
  are kept on an exact clock that does not depend on the project's sample
  rate, so changing the rate later will not shift a word or a sync point.
- Audio files at an unusual sample rate the exact clock cannot hold (for
  example 37.8 kHz) are refused at import with a message saying to convert
  them first. Every common rate, 8 to 192 kHz, works.
- Projects from earlier development builds keep their sync groups when they
  are upgraded.

## [v26.10.16.5] - 2026-10-16

The project format kuulas will keep (format version 1). There is still no
app to open; this is what the app will save into.

- A project is a `Name.kuulas` folder: one database for every edit and its
  history, the audio beside it, rebuildable caches, and automatic backups.
- Transcripts, media and their names are shared by every edit of a project:
  a transcript correction made in one edit shows in all of them, and can be
  undone, unless someone has changed the same transcript again since (then
  kuulas refuses rather than throwing that change away).
- Every history step records who made it and on which computer, with an id
  that stays unique when a copy of the project comes back from a reviewer.
  Steps can be named (checkpoints).
- Opening a project that is open on another computer (via Dropbox or
  similar) opens it read-only, instead of corrupting it. A project left
  locked by a crash is taken over after two minutes, with a warning.
- Automatic backups every 10 minutes while there are changes: the last 12,
  plus the last one of each day for two weeks, in the project's `backups/`.
- A project made by a newer kuulas opens and keeps everything this version
  does not understand; one that needs a newer kuulas is refused with a
  message saying which version made it.
- Projects made by earlier development builds are upgraded on open, after a
  backup copy of their database.
- `kuulas info <folder>` shows a project's format, sizes, media (linked,
  copied, missing) and backup count.
- Waveform data is a cache: deleting `caches/` is safe; it is rebuilt.

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
