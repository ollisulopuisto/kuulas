# Music is not transcribed

Owner request, 2026-10-20: do not transcribe files on music channels.

## The rule

A recording is **skipped** when every clip that uses it is on a track whose `kind` is
`music`.

- On a speech track and a music track: still transcribed (the speech clip needs the words).
- Used by no clip: transcribed as before.
- Pure helpers: `src/kuulas/transcribable.py` and `ui/transcribable.js` (same rule, both tested).

## Where it applies

- Server: `Session.transcribe` refuses skipped recordings with `error.transcribe.music_only`
  unless `force` is set (`POST /api/transcribe {"force": true}`). Every route goes through it:
  menu commands, the panel, "transcribe all", the Colab batch (so music audio is never
  uploaded to Google by default). `Session.restart_background` re-checks, unless the job was
  created forced (`forced` in the job file).
- UI: Text > Transcribe commands drop music-only recordings (a music-only track gives a
  notice, no job); the panel's offer list already excluded music tracks.
- Panel: a selected clip of a music-only recording without words shows "Music track: not
  transcribed" and a local-only "Transcribe anyway" (sends `force`; never Colab).
- No automatic transcription exists (after import or on open), so nothing to guard there.
- Existing transcripts of music recordings are kept and shown; nothing is deleted.
