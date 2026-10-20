# Ducking: a track property now, a clip property possible later

Decision (owner, 20.10.2026): **"Duck under speech" is a track property.** This page
records why, what is stored, and the way out: how to move to clip-level ducking later
without losing anyone's sessions.

## Why the track

- Music and sound effects share a role (`Track.kind == "music"`) but not a need: a
  music bed should duck under speech, a loud effect should not.
- One switch per track covers the common case with no clicking. Roles come from the
  bus (see bus roles), the duck switch from the track, so a template of two speech
  tracks and two music tracks needs nothing more.
- A single music track that ducks in one scene and stays loud in another is the case
  clip-level ducking would serve. It stays possible by hand (envelope points).

## What is stored

1. `Track.duck: bool | None = None`. `None` means the role's default: music ducks,
   speech does not apply. Optional field: an older reader keeps it in `extra` and plays
   the track unducked (FORMAT.md rule for optional fields).
2. The ducking itself is **ordinary automation**, never a hidden effect:
   `Track.automation` (timeline frames) written by one command (Track > Auto > "Duck
   music"), one undo step, editable by hand afterwards. The flag only says which tracks
   the command, and the export, treat as ducking tracks.
3. Export: Kuulas writes the ducking into the track gain automation of the stems and
   passes `--no-music-duck` (Done in Kuulas, same registry as the music level and the
   block levels). Tracks with `duck == False` are left alone.

Because the result is automation points, not a flag the renderer interprets, the
mixer, export, stems and undo need no special case.

## The way out: migration to clip-level ducking

Clip-level means the ducking lives in each clip's `Clip.envelope` (source frames, so it
follows the clip when it is moved) and there is no track flag. The data allows this
without loss:

- **Track to clip (forward, lossless):** for each clip on a ducking track, cut the
  track's `automation` to the clip's timeline window, convert the points to the clip's
  source frames (`frame - clip.start + clip.in`, speed 1; handle each clip's offset and
  length), add the boundary values at the clip edges so the curve is identical, merge
  into `Clip.envelope` (existing envelope points win where they coincide), then clear
  `Track.automation` and `Track.duck`. The mix must render **bit-identical** before and
  after: this is the migration's test.
- **Clip to track (backward, lossy, not offered):** clip envelopes cannot in general be
  merged into one track curve. If ever needed: only where every clip of the track
  agrees.
- **Where it runs:** a forward-only migration `migrate_N_to_N+1(db, folder)` in
  `src/kuulas/migrations.py` (FORMAT.md, "Compatibility and migrations"): it bumps
  `package.VERSION` and `db.SCHEMA_VERSION`, takes the automatic
  `backups/pre-migration-vN-*.sqlite` snapshot first, rewrites every history node's
  state, and an older Kuulas refuses the newer project (`min_reader`), never half-reads
  it.
- **Interim safety:** keep Track-level automation as "the ducking" until migration; do
  not write ducking anywhere else (no per-clip flags next to the track flag), so there is
  one place to migrate from.

## Open

- Whether the stems should carry track gain at all (today they are "dry": clip gain
  applied, track gain and bus not). Needed for the owner's SFX-versus-music contrast
  set with track gain; decided separately.
- Duck depth and threshold per project (automixer defaults: threshold -30 dB, ratio 8)
  as dialog fields.
