# Changelog

## [v26.10.16.8] - 2026-10-16

Playback exists, though there is still no app to press play in (the HTTP
API comes next). Not yet tried on real speakers: run
`uv run pytest -q tests/hardware -s` on the Mac and on Windows before
relying on it.

- Plays the project through the computer's default output (CoreAudio on a
  Mac, WASAPI on Windows), with the same mix as export. Play from anywhere,
  play a selection and stop at its end, stop, jump while playing; an edit
  made during playback is heard within one buffer (about 21 ms).
- The playhead position reported is what you are hearing, not what was
  just computed, so the display does not run ahead of the sound. Stopping
  leaves the playhead where you heard it.
- Audio problems cost a moment of sound, never the session: a block that
  fails plays as silence and is reported; a stream that dies or freezes
  (headphones unplugged, Bluetooth dropping) is reopened on the current
  output and playback pauses with a message; if playback falls behind, the
  buffer is doubled and a "playback is struggling" message appears instead
  of silent stuttering. A device that cannot play the project's sample
  rate gets converted audio, with a note; exports are unaffected.
- A recording whose stored audio is damaged in one place plays silence
  there, plays normally elsewhere, and is marked damaged with a message
  naming the file and the time. (Rebuilding it from the original is not
  offered yet.)
- Reference renders of eight small test projects now pin down what the
  mixer sounds like; any future playback engine must reproduce them.
- New dependency: soxr (sample-rate conversion for playback only).
- Not yet: following a change of the default output while the old one
  still works (picked up at the next play after half a minute idle).

## [v26.10.16.7] - 2026-10-16

There is still no app to open; this is the layer the app will talk to.

- Opening a project now gives one place that every change goes through:
  edit, undo, redo and jump to any earlier step, each change saved before it
  is acknowledged. Reopening after a crash resumes at the last edit.
- Importing several files at once puts each on its own track (mono as
  speech, stereo as music) as one undo step. Files imported together are
  treated as recorded together: placed by the recorder's own clock when the
  files carry one, and grouped in sync.
- Transcripts can be set and corrected as undoable steps; deleting words
  cuts the same stretch from every track.
- Auto-silence (optionally for chosen tracks), automix, relink and
  consolidate are available as project commands.
- Clicking solo through the tracks is a single undo step, and mute clicks
  on one track merge, instead of one step per click.
- Fixed: importing the same audio twice in one batch could clash while
  both copies were being encoded; the second now waits for the first.

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
