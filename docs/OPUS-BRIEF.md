# Brief for Opus 5.5: focus view and the kuulas file format

Written by Haiku 5.5 from the owner's notes, for an Opus session to decide
and turn into plan changes. Nothing here is decided. Read `docs/PLAN.md`
(ground rules, WP4, WP18, WP21, WP27) and `ROADMAP.md` first.

## 1. Focus mode: one track at a time

The owner wants to work on one track without the others getting in the way.

Questions to decide:

- **What "focus" shows.** Proposal: the focused track fills the lane area;
  the others collapse to thin strips (their names and a half-height waveform
  at about 12 px), so their timing stays visible for sync. Alternatives:
  hide them entirely (loses sync context), or dim them.
- **Auto-shrink.** When a track gains focus, every other lane shrinks to the
  thin strip height, and returns when focus is released. Make it a setting
  and make the animation respect reduced motion.
- **Entering and leaving.** A key (proposal: `F`) toggles focus on the
  track under the focus cursor; Esc leaves it. Focus is UI state, not history.
- **Solo vs. focus.** Solo changes what is heard; focus changes what is seen.
  Decide whether focusing a track also soloes it (proposal: no, but offer it
  as one key).

Other ideas to weigh, from the same brief:

- **Speaker focus:** focus on a speaker rather than a track; all tracks
  with that speaker (WP22) expand together, including a Zoom track.
- **Transcript follows focus:** the transcript panel filters to the
  focused speaker's words, and clicking one plays from there.
- **Clip-level focus:** zoom the timeline to the selected clip's extent
  with its neighbours as thin strips, for precise trimming.
- **Ducking view:** in focus, show the ducking curve of the focused track
  as a larger band under its waveform, so the automation can be edited there.
- **Focus history:** a small "back" stack, so Shift+Tab returns to the
  previous focus, like Mod+Z for view changes.

Decide which of these go in the first version (suggest: focus, auto-shrink,
speaker focus) and which are v2.

## 2. A kuulas file format, better than the Hindenburg one

kuulas already imports and exports `.nhsx`. The owner wants its own format,
designed carefully, and asks what it needs: sync, transcripts, and the rest.

Current state (what the code stores today):

- A project folder: `project.sqlite` (history nodes as compressed JSON
  states, transcript revisions, meta) plus `media/` (per media: `.json`
  metadata, `.flac` working file or a link to the original, `.peaks.npy`,
  `seen.json`, optional `originals/`).

Requirements the format must meet:

1. **Sync.** Each media's clock: BWF `time_ref` and sample rate; each clip's
   `sync_origin` and group; each group's main media. Sync must survive a
   change of project rate (WP27) and a re-import.
2. **Transcripts.** Word-timed in source frames per media, with speaker,
   revisions (corrections are new revisions), and the engine that made them
   (faster-whisper model name and version, or "imported: <tool>").
3. **Markers and cut candidates.** Anchored to the recording clock (WP18), so
   they survive every edit. Their accept/reject state is per edit (WP21).
4. **Several edits** (WP21): shared media, transcripts and sync; separate
   tracks, clips, markers' state, and undo trees.
5. **History.** Whole-state nodes (current design) or a log of operations.
   Decide which: whole states are simpler and crash-safe; a log is smaller
   and gives a real audit trail. Note the cost of each at 5,000 edits.
6. **Media.** Content-addressed (SHA-256), with linked and copied cases,
   remembered paths, and relink (WP19 / WP20).
7. **Caches** (peaks, onsets, analysis, excerpts) keyed on the hash of their
   inputs and parameters, and rebuildable at any time (ground rule 8).
8. **Forward and backward compatibility.** A format version, a minimum
   reader version, and unknown keys preserved on save, so an older kuulas
   does not destroy a newer project's data.
9. **Hindenburg round-trip.** Fields kuulas does not model are kept in an
   opaque per-clip or per-track blob, so a `.nhsx` round trip loses nothing.
10. **Portability.** The project must be copyable to another machine as one
    folder, and must say which media are missing without crashing.

Questions to decide:

- **One file or a folder.** Proposal: a macOS-style package folder, named
  `<name>.kuulas`, holding `manifest.json` (format version, min reader,
  created/modified, project rate), `project.sqlite`, `media/`, `caches/`.
  Alternative: a single SQLite file with media in blobs. Compare copy time,
  Dropbox/Syncthing behaviour, and bloat.
- **Where the manifest lives** and whether it is written last (atomic
  replace) so a half-saved project is detectable.
- **Schema:** tables for `edits`, `tracks`, `clips`, `markers`, `media`,
  `sync_groups`, `transcript_revisions`, `words`, `nodes`, `caches`. Or keep
  project state as one JSON document per node (current). Recommend one.
- **Backups:** an automatic snapshot of `project.sqlite` every N minutes
  while open, keeping the last M, and never over the live file.

Deliverable for the Opus session: a short design document
(`docs/FORMAT.md`) with the chosen layout, the schema, the version rules and
a migration path from today's folder, plus WP changes in `docs/PLAN.md` and
new R-rows in `ROADMAP.md` for the decisions the owner must make.
