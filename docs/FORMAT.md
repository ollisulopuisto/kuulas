# The kuulas project format (v1)

Decided by Opus 5.5 from `docs/OPUS-BRIEF.md`. Owner decisions that remain
open are listed at the end and in `ROADMAP.md`. Implemented by WP29 and WP30
in `docs/PLAN.md`.

## Decisions in one screen

1. **A package folder** `Name.kuulas/`, not a single file.
2. **Two kinds of state**, kept apart:
   - **Material** is shared by every edit: media, sync groups, transcripts,
     music metadata, the project rate.
   - **Edit state** is per edit: tracks, clips, buses, markers, master.

   Today a transcript pointer sits inside each edit's state. That is wrong
   for several edits (WP21), and the format fixes it.
3. **Two clocks:**
   - Things that describe the *edit* are in **project frames** (integers at
     the project rate), as now.
   - Things that describe a *recording* (sync origins, BWF start times,
     transcript words, onsets, marker anchors) are in **flicks**: integers of
     1/705 600 000 s.

   Flicks divide every audio rate (8k, 16k, 22.05k, 32k, 44.1k, 48k, 88.2k,
   96k, 192k) and every video rate, 29.97 included, exactly. Recording facts
   therefore never change when the project rate changes (WP27 converts edit
   state only), and never round.
4. **History keeps whole states**, stored once each by content hash. Each
   step also stores the edit that made it (name and arguments) as an audit
   trail; it is never replayed. Measured sizes are below.
5. **Never destroy what you cannot read.** Every object carries the keys
   this version does not know into the next save unchanged. A Hindenburg
   round trip and an older kuulas both lose nothing.
6. **SQLite for state, plain files for audio.** Media files are immutable
   and content-addressed. The database is the only thing that changes while
   editing.

## Why a folder, not one file

| | Package folder | One SQLite file with audio inside |
|---|---|---|
| Linked media (left in place) | works: the files stay where they are | impossible, so everything is copied in |
| Save cost | only the database pages that changed | the same, but the file is gigabytes |
| Dropbox, Syncthing, backups | audio uploads once and never changes; only `project.sqlite` churns. The lock is one small file per machine (see "locks/"), so a sync service never sees two machines write one file | a multi-GB file changes on every edit |
| Copy to another machine | copy one folder (consolidate first if media is linked) | copy one file |
| Corruption blast radius | a damaged database loses edits; audio is safe | everything at once |

On a Mac, the folder becomes a document package (one icon in Finder) once
the desktop app (WP15) declares the type. On Linux and Windows it is a plain
folder named `Name.kuulas`.

## Layout

```
Name.kuulas/
  manifest.json        format identity; written at create and on upgrade only
  project.sqlite       all state: material, edits, history (WAL mode)
  locks/               who has it open: one file per open instance (empty when closed)
  resume.json          where the user left off (not project state; see "resume.json")
  clipboard.json       this project's clipboard (not project state; see "clipboard.json")
  media/
    <media id>.flac    working file (absent for linked media)
    excerpts/          WP20 excerpts, same naming
    originals/         kept originals (copy=True of lossy/resampled sources)
  caches/              rebuildable at any time; safe to delete; never archived
    peaks/  onsets/  analysis/  render/
  backups/             automatic snapshots of project.sqlite
  recordings/          WP12 takes (WAV), linked in place like any media
```

## manifest.json

```json
{
  "format": "kuulas-project",
  "version": 1,
  "min_reader": 1,
  "created_utc": "2026-10-16T16:45:00Z",
  "written_by": "kuulas 26.10.16.4",
  "id": "a 128-bit random hex id",
  "copy": "a 128-bit random hex id, new for every hand-off copy",
  "lineage": ["copy ids this copy descends from, oldest first"]
}
```

- Written with write-to-temp, fsync, then rename. It changes only when the
  project is created or its format is upgraded, so sync tools do not churn
  on it.
- `version` rises with every format change. `min_reader` rises only when an
  older reader would misread the new data. The rules are under "Compatibility".
- `id` identifies the project when the folder is renamed or copied. A copy
  keeps the id; "Save as copy" mints a new one.
- `copy` and `lineage` identify **hand-off copies** of one project (A sends
  v1 to B, B sends v2 back; see "Review round trips"). Two copies with the
  same `id` and a shared history step can be merged.

## locks/

One file per open instance: `locks/<hostname>-<instance uuid>.json`,
`{"host", "pid", "user", "instance", "opened_utc", "heartbeat_utc"}`. The
hostname is reduced to `A-Za-z0-9._-`. A machine only ever writes its own
file, so a sync service (Dropbox, Syncthing, iCloud) has nothing to
conflict on and never makes a "conflicted copy". The heartbeat is rewritten
every 60 s while open; close deletes the file.

On open, kuulas reads every file in `locks/`:

- a lock of **another host** whose heartbeat is under 5 minutes old (room for
  sync delay of minutes) refuses the open: it opens **read-only** with a
  banner naming that host;
- a lock of **this host** is fresh for 2 minutes, and dead at once when its
  pid no longer runs (a crashed window is taken over without waiting);
- older locks are ignored (with a warning) and deleted once over 1 hour old;
- unreadable files (half-synced) and any file whose name contains
  "conflicted copy" (in `locks/` or the project folder) are not locks and are
  ignored, never an error.

Heartbeats compare the writer's clock with the reader's, so a machine whose
clock is minutes off can look stale or fresh wrongly. Keep both on network
time.

**Legacy `lock.json`.** Older kuulas wrote one shared `lock.json`. It is still
read (a fresh one from another host or a live process still blocks the open)
but never written; it is deleted when stale. No `min_reader` change: an old
kuulas on a new project would not see the `locks/` files and could open a
project this one holds, so keep all machines on the same version.

**SQLite side files.** `project.sqlite-wal` and `-shm` are synced by Dropbox
independently of the main file, so another machine can see a half-written
set. kuulas runs `wal_checkpoint(truncate)` after a write burst (a tick with
no new writes) and on close, so a closed project's main file is complete and
the side files are empty. On macOS it also sets the Dropbox ignore attribute
(`xattr -w com.dropbox.ignored 1`) on the side files and `caches/`, best-effort,
on every open (SQLite recreates the files, which drops the attribute). `locks/`
is never marked: it must sync.

**As built (lock for synced folders).** The shared `lock.json` is replaced by
`locks/` (one file per instance, see above): heartbeat 60 s, another host is
stale after 300 s, a dead pid on this host at once, stale locks over 3600 s
are swept, "conflicted copy" files are ignored. The WAL is truncated after a
quiet tick and on close; `caches/` and the side files carry the Dropbox
ignore attribute on macOS. `min_reader` and `version` are unchanged. Not
verified against a real Dropbox.

## resume.json

`{"version": 1, "saved_at", "host", "user", "playhead", "in", "out",
"focus_track", "zoom", "scroll"}`: where the user left off, so the position
travels with the project through Dropbox to the other Mac. `saved_at` is UTC
(`2026-10-18T19:00:00Z`); positions are frames, `zoom` frames per pixel. Fields
that are not valid numbers/strings are left out.

**Not project state.** Never in the history or the database, no undo step, no
change to the bytes of `project.sqlite`. Opening a project does not write it;
it is a convenience whose loss costs nothing. The server rewrites it atomically
(temp file, fsync, rename) whenever the view memory is saved, at most once every
5 s (a trailing write keeps the last position), at once on Mod+S, on page hide
and on close. Only the instance that holds the lock writes (a read-only open
never does). A write failure is a logged warning, never an error.

On open the UI restores from the newer of this file and the per-user view
memory (`saved_at`). A damaged file, or one without `saved_at`, is ignored; so
is any file with "conflicted copy" in its name (only the exact name
`resume.json` is read). `syncmark.py` leaves it alone: it must sync.

## clipboard.json

`{"entries": [Entry, ...]}`, newest first: the project's own clipboard (WP46,
WP65). An entry is a snapshot of copied clips as references (media SHA-256,
source offset and length, gain, pan, fades, envelope, layout), never audio, plus
the metadata the panel shows and later sorting and search use: `id`, `name`,
`created_utc` (epoch seconds, UTC), `span`, `source_project` (the folder it was
copied in), `pinned` (kept for compatibility; the UI no longer pins), and the
keys below. Unknown keys are kept and written back.

Metadata kept for sorting and searching (all optional; an entry without them
loads with the defaults):

| key | meaning |
|---|---|
| `source_name`, `source_id` | the source project's name (folder stem) and manifest `id` |
| `tracks`, `track_kinds` | the names and kinds of the source tracks, by slot |
| `text` | the transcript words inside the copied stretch, one line per track, original case (search lowercases) |
| `shared` | `true` when marked as worth sharing across projects (WP65 step 4) |
| `adopted_from` | the folder of the project an adopted copy came from |
| `refs[].media_name` | the recording's file name when copied (never an identity; the hash is) |

**Not project state.** Never in the history or the database, no undo step, no
change to the bytes of `project.sqlite`. The file is rewritten atomically
(temp file, fsync, rename) on every copy, cut, rename, delete and clear. Only the
instance that holds the lock writes it; a read-only open keeps its clipboard in
memory and never writes. A write failure is a logged warning, never an error;
nothing the user copied is dropped for size (the only prune is the explicit
"Clear old entries").

**It must sync.** The clipboard travels with the project through Dropbox to the
other Mac, so `syncmark.py` never marks it and it is not in any ignore list. Only
the exact name `clipboard.json` is read; a file with "conflicted copy" in its
name is another file and ignored. A damaged file reads as an empty clipboard (and
is replaced by the next write).

**Browsing and adopting (WP65).** The Clipboard tab can list another project's
clipboard. That is read-only: kuulas reads only `<folder>/clipboard.json` of
that project, never takes its lock, never opens its database. The folder must
be an absolute path with no `..`, an existing `*.kuulas` folder (links resolved)
holding a `manifest.json`; `clipboard.json` itself must be a plain file, not a
link. A missing, damaged or oversized file is an empty list, never an error.
Adopting copies an entry into the open project's own clipboard with a new id and
`adopted_from` set (the original's `created_utc` is kept in `adopted_created_utc`).

The per-user file `clipboard.json` in the config folder (or
`$KUULAS_CLIPBOARD_FILE`) has the same format and is the **shared** store: the
entries the user marked as worth sharing across projects (WP65).

## Database schema (`project.sqlite`, WAL, `synchronous=FULL`)

```sql
-- Identity and versions inside the database too, so a lone .sqlite is
-- recognisable.
meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)
  -- schema_version, project_id, project_rate, settings (JSON, WP27)

-- Content-addressed storage for every JSON state and word list.
blobs(hash TEXT PRIMARY KEY,           -- sha256 of the uncompressed bytes
      kind TEXT NOT NULL,              -- 'edit-state' | 'material' | 'words' | ...
      data BLOB NOT NULL)              -- zlib(level 6) of canonical JSON

-- ---- material: shared by all edits ---------------------------------------
media(id TEXT PRIMARY KEY,             -- 'm' + sha256[:12]
      sha256 TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      storage TEXT NOT NULL,           -- 'linked' | 'working' | 'excerpt'
      channels INTEGER NOT NULL,
      source_rate INTEGER NOT NULL,    -- the file's own rate
      source_frames INTEGER NOT NULL,  -- at source_rate
      subtype TEXT,                    -- PCM_16 / PCM_24 / ... of the working file
      lossless INTEGER NOT NULL,
      time_ref_flicks INTEGER,         -- BWF start on the recorder's clock, or NULL
      linked_path TEXT, linked_size INTEGER, linked_mtime_ns INTEGER,
      linked_package_rel TEXT, linked_series_rel TEXT,
      excerpt_of TEXT, excerpt_start_flicks INTEGER,
      tags TEXT NOT NULL DEFAULT '{}', -- music metadata etc. (JSON, WP25)
      extra TEXT NOT NULL DEFAULT '{}',-- unknown keys, preserved
      added_utc TEXT NOT NULL)
media_paths(sha256 TEXT, path TEXT, first_seen_utc TEXT, last_seen_utc TEXT,
            PRIMARY KEY (sha256, path))   -- replaces seen.json

-- Material changes are versioned like edits, so they can be undone.
material_revs(id INTEGER PRIMARY KEY, parent INTEGER, label TEXT NOT NULL,
              root TEXT NOT NULL REFERENCES blobs(hash), created_utc TEXT)
  -- the material root blob holds: sync groups and their members, the
  -- transcript revision in use per media, speaker names per media.
transcript_revs(id INTEGER PRIMARY KEY, media TEXT NOT NULL, parent INTEGER,
                words TEXT NOT NULL REFERENCES blobs(hash),
                engine TEXT NOT NULL,  -- JSON: {"tool","model","version","language"}
                created_utc TEXT)

-- ---- edits: one undo tree each --------------------------------------------
edits(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_utc TEXT,
      archived INTEGER NOT NULL DEFAULT 0, head TEXT)  -- a nodes.id
nodes(id TEXT PRIMARY KEY,           -- UUIDv7: unique across copies, time-ordered
      edit TEXT NOT NULL REFERENCES edits(id),
      parent TEXT,
      author TEXT NOT NULL,            -- the person's name from settings
      machine TEXT NOT NULL,           -- host name, for "who did this where"
      label TEXT NOT NULL,
      op TEXT NOT NULL,                -- JSON {"name","args"}: audit trail only
      state TEXT NOT NULL REFERENCES blobs(hash),
      material_from INTEGER, material_to INTEGER,  -- set when this step changed material
      context TEXT,                    -- JSON UI context for stateful undo (WP8)
      created_utc TEXT NOT NULL)
checkpoints(node TEXT PRIMARY KEY REFERENCES nodes(id),
            name TEXT NOT NULL,          -- "v1 sent to Ville for review"
            kind TEXT NOT NULL,          -- 'manual' | 'sent' | 'received'
            copy TEXT,                   -- the hand-off copy id, for sent/received
            created_utc TEXT NOT NULL)
```

**Why UUIDs, not integers, for steps:** two copies of a project grow their
histories apart, and integer ids would collide when B's steps come back to
A. UUIDv7 ids are unique everywhere and still sort by time. This must be in
v1: changing ids later means rewriting every history.

Material is in the database as rows (media) and a versioned root blob
(sync, transcript pointers). A material change made from an edit is a node
in that edit's tree with `material_from` and `material_to`. Undoing it
moves the material head back, but only if the material head is still
`material_to`. Otherwise someone changed it again since, so kuulas refuses
and offers the history panel. Edit state no longer holds a transcript
pointer (`Project.transcripts` moves out).

## What is stored where

| Thing | Where | Unit |
|---|---|---|
| clip start, length, offset, fades, crossfades, envelopes, automation | edit state | project frames |
| a track's gate: `Track.gate`, Auto-Silence's merged closed ranges (WP44) | edit state | project frames |
| tracks, buses, master, layers, roles, tags | edit state | — |
| markers (WP18) | edit state | anchor in flicks on a recording clock; timeline markers in project frames |
| cut candidates (WP18, as built) | material root `candidates` | flicks from the anchor media's start |
| sync groups: main media, members, each member's origin | material | flicks |
| BWF start time | media row | flicks |
| transcript words (`w`, `s`, `e`, `spk`, `conf`) | words blob, per revision | flicks from the media's start |
| which transcript revision a media uses | material root | — |
| music metadata | media row `tags` | — |
| onsets, peaks, analysis | `caches/` | onsets in flicks; peaks per 256 working frames |
| project rate, settings | `meta` | — |

**Sync per media, not per clip.** Marking clips in sync already makes the
whole file join (ops.mark_in_sync), so membership belongs to the media:
`{group: {main: media_id, members: {media_id: origin_flicks}}}`. A clip's
recording position is `origin + offset`, converted to flicks. Excerpts
(WP20) inherit their original's origin plus `excerpt_start_flicks`.
Subclips need no per-clip fields, so `Clip.sync` and `Clip.sync_origin` go
away (WP30).

## Review round trips (A edits, B reviews, A decides)

The workflow: A makes a rough edit v1 and sends it to B. B makes more
edits. Some are **unconditional** (just done) and some **conditional**
(suggestions for A). B sends v2 back, and A reviews what B did.

- **Suggestions live in edit state**, like markers, anchored to the
  recording clock so they survive every later edit:

  ```
  Suggestion(id, author, kind, anchor, payload, note, state, base_node)
    kind:   'cut' | 'restore' | 'gain' | 'mute' | 'unmute' | 'note' | 'take'
    anchor: recording ranges (group or media, flicks), as markers
    payload: e.g. {"gain_db": -3.0}, {"take": 2}
    state:  'open' | 'accepted' | 'rejected'
  ```

  Only these kinds can be conditional. They are the ones that can still be
  applied correctly after other edits, because they name recording ranges,
  not timeline positions. Anything else B does is unconditional.
- **Accepting** a suggestion applies its edit as a new step by A
  ("accepted Ville's cut"), and **rejecting** keeps it in the list as
  rejected. Both are undoable.
- **Coming back:**
  - If A did nothing since sending, opening v2 simply continues the history:
    B's steps follow A's checkpoint, each marked with B as author.
  - If A kept editing meanwhile, B's *unconditional* changes are turned
    into suggestions too: the changes view's diff (recording ranges present
    in one and not the other, plus gain, mute and take changes) gives the
    items. A reviews everything B did, and nothing B did is lost or applied
    blindly. B's history steps are kept as an abandoned branch for reference.
- **Hand-off copy:** "Send for review" writes a checkpoint, then a copy of
  the package with a new `copy` id and media by one of three rules:
  - none: B relinks by hash from their own files;
  - used ranges plus 2 s handles (WP20 excerpts; the default);
  - everything.

  Never the locks, backups or caches.

## People, interviews and bits (from the start)

Transcripts must know *who* speaks and *which interview* a recording belongs
to, so the same interview recorded by several people (A's mic, B's mic, the
Zoom mix) links together, and everything a person said can be found.

- **Person** `{id (UUIDv7), name, aliases[], role ("host" | "guest" | …),
  notes, extra}`.
- **Interview** (recording session) `{id, title, date (ISO date, optional
  UTC time), place, participants: [{person, role}], media: [media sha256],
  sync_group, notes, tags[], extra}`. All files that captured one sitting
  belong to it; it usually matches a sync group.
- **Who speaks:** a single-person mic file has `media.person`; a mix file
  (Zoom, phone) has a per-transcript-revision map from the transcription's
  speaker labels to people. Stored words keep `spk` as given and gain
  `person` (resolved through the map), so a corrected map changes nobody's
  words.
- **Bit** (index card) `{id, interview, from_flicks, to_flicks (on the
  interview's recording clock, so it covers every mic), title, summary,
  people[], tags[], status ("idea" | "selected" | "used"), color, notes,
  placements: [{project, edit, outline_index}], extra}`.
- **Where they live:**
  - in a series: one small JSON file per item under `Series/people/`,
    `Series/interviews/`, `Series/bits/`, each written atomically by
    write-temp-and-rename. A sync conflict only ever touches one item, and
    kuulas shows conflicted copies;
  - outside a series: the same records in the project's material root.

  Projects refer to them by id.

**As built (WP41, format version 2).** The material root gains `people` and
`interviews` (id -> record), `media_person` (media id -> person id) and
`speakers` (transcript revision -> {speaker label: person id}). `person` is
resolved when words are read and never written into the stored words, so a
corrected map rewrites nothing; a new transcript revision starts with an
empty map. Interview `media` holds sha256 digests. The version-1 to 2
migration adds the empty keys to every material revision in place, so
`material_from`/`material_to` and undo are unchanged. A series item is
`<uuid>.json`; a file with anything after the uuid (Dropbox, Syncthing,
iCloud, OneDrive copies), an unreadable file, or one whose id differs from
its name is reported by `SeriesStore.conflicts()` and never read as an item.

**As built (WP44, format version 3).** A track gains `gate`: a list of
`[start, end)` project-frame pairs, sorted, non-overlapping and not touching
(`gate.normalise`). Where it is closed the track is silent whatever its clips
say; the 30 ms edge ramps are derived by the mixer and never stored. Auto-Silence
writes it instead of splitting clips, and running it again replaces the track's
gate. It is part of the edit state, so history keeps it as it keeps clips (a
ripple delete shifts and trims it in the same step). An empty gate is not
written, so a track that never had one keeps its bytes and its state hash, and
old projects load with an empty gate. Old projects that contain Auto-Silence
clip pieces (muted clips with baked fades) keep working unchanged.

**As built (derived mute ramps).** The 30 ms ramp on an open clip edge that
touches a muted piece (same track, same media, contiguous source) is derived
by the mixer and never stored: `mute_ranges`/`mute_range` write no fades, so
unmuting restores the clips and their render exactly. Where an older project
stored that fade, the longer of stored and derived applies, so it renders as
before.

*Version and `min_reader`.* The version rises to 3 (additive field, the 2 to 3
migration rewrites nothing). An older reader would keep `gate` in `extra` and
play the track ungated, which is audible, so a project that holds a gate must
not open there: `min_reader` rises to 3 **for that project, when its first gate
is committed**, and the manifest is written before the state that carries the
gate (a crash between the two leaves a stricter manifest, never a gate an old
reader plays wrongly). Projects that never get a gate stay at `min_reader` 1.
It is never lowered again, even if the gate is cleared, because older history
steps may still hold one. An upgrade of a version-2 project keeps whatever
`min_reader` it already asks for.

*Measured.* A state with 4,800 gate ranges (4 mics, a range every 3 s for an
hour, twice a busy hour) packs in about 7 ms (9 KB); 19,200 ranges (a range
every 0.75 s on every mic) take 56 ms, which no real hour reaches. The 300 s
four-voice test conversation (198 ranges) packs to 1.7 KB with the gate
against 8.1 KB with the clip pieces it replaces.

**As built (WP19h markers, regions, chapters).** The edit state gains an
optional `Project.markers`: a list of `{"id", "name", "start", "end"?, "kind"}`
sorted by `start`, in project frames (timeline markers, not recording anchors:
the WP18 table row above is about recording-clock anchors, which this does not
build). `kind` is `"marker"` (a point), `"chapter"` (a point that goes in the
chapter list) or `"region"` (a range `[start, end)`; only a region has `end`).
The key is absent while the list is empty, so a project that never had a marker
keeps its bytes and its state hash and old projects load with none.

- **Ripple.** A ripple delete moves them with the audio, but only when every
  track is cut (a scoped cut moves other tracks' audio less than the timeline
  the marker sits on): a point inside the cut goes to the cut start, a region
  loses the overlap and goes if nothing is left. An insert paste on every
  track opens the same gap (`markers.open_gap`): later points move right, a
  region that straddles the point is stretched.
- **Chapter list.** Only kind `chapter` is listed (`GET /api/chapters`); two
  chapters on one frame (a ripple can bring them there) make the export refuse
  with a translated error rather than drop one.

*Version and `min_reader`.* `min_reader` does not rise and `version` does not
change. Markers change no sound, so an older reader plays and exports exactly
what this one does. Such a reader keeps the `markers` key in `Project.extra`
and writes it back (the unknown-field rule above), so nothing is lost; what it
cannot do is move them when it ripples, so markers saved by it after a
ripple cut can sit later than their audio. That only matters for a build older
than this one editing a project that has markers, and the cost is a wrong
position, not lost data, so refusing to open (as a gate does, where the cost
is audible) is not worth it.

**As built (WP43 narration placeholders).** The edit state gains an optional
`Project.placeholders`: a list of `{"id", "track", "start", "length", "text",
"estimated", "language"?}` sorted by `start`, in project frames. A placeholder
is script text standing for `length` frames from `start` on one track, to be
recorded or imported later in place. It is **not a clip**: a clip without media
would break every reader of `Clip.media` (mixer, usage, music report, gate, the
transcript), so it is a separate per-track collection, like markers but with a
`track`. The key is absent while the list is empty, so a project that never had
one keeps its bytes and its state hash. `language` is absent while empty.

- `estimated` is true while `length` comes from the text
  (`narration.estimate_frames`, about 2.3 words a second); editing the text
  then re-estimates. A hand-set length, or a ripple cut that trimmed the
  placeholder, clears it and the text no longer moves the length.
- **Ripple.** It follows its own track, not the whole timeline (unlike a
  marker): a ripple delete on a set of tracks moves, trims or removes the
  placeholders on those tracks (`placeholders.ripple`), and an insert that
  opens a gap on a track (`paste_apply._open_gap`) moves the later ones and
  stretches one that straddles the point (`placeholders.open_gap`). Deleting a
  track deletes its placeholders.
- **Silence.** The mixer, usage and the music report read clips only, so a
  placeholder plays as silence and counts as nothing audible. `Project.length`
  ignores it.
- **Replace with a take** (`ops.replace_placeholder`, the session command
  `placeholder_take`): the placeholder becomes a clip at the same start on the
  same track, and the later material of the tracks `edit_scope.expand_range`
  names moves by the take's length minus the placeholder's (a gap opened where
  the placeholder ended, or a ripple delete of the leftover); one undo step.
- **Export.** The result of `export` carries `placeholders_skipped`: the
  unrecorded placeholders inside the exported range. It is a warning, never a
  refusal.

*Version and `min_reader`.* Neither changes. A placeholder changes no sound, so
an older reader plays and exports the same audio; it keeps the `placeholders`
key in `Project.extra` and writes it back, but cannot move them when it
ripples, so placeholders saved by it after a ripple cut can sit later than the
material around them (a wrong position, not lost data, as for markers).

**As built (WP18 cut candidates).** The material root gains an optional
`candidates`: candidate id -> record

```
{"kind": "silence" | "filler" | "retake" | "breath" | "marked",
 "media": media id,        # the anchor recording
 "start": flicks, "end": flicks,   # from that media's start, like transcript words
 "scope": "track" | "group",
 "state": "open" | "cut" | "kept",
 "score": 0..1, "reason": {"key", "params"}, "text": the words under it}
```

- **Anchoring.** A candidate names a recording range, never a timeline
  position; its timeline spans are derived from the clips every time
  (`candidates.place`), so it follows its audio through every move, trim
  and cut, and a fully cut-away candidate simply has no spans. A `group`
  candidate (a pause nobody in a sync group fills, or a mark over a clip in a
  group) is anchored to the group's **main** media and covers every member,
  each through its origin; a `track` candidate (a filler, a retake) covers
  only the clips of its own media.
- **Ids** are `"k" + sha256("<media sha256>|<kind>|<start>|<end>")[:16]`: a
  second detection finds the same ids and keeps their decisions. A new
  candidate overlapping a `cut` or `kept` one (or a mark) is not added, so a
  rejected stretch is not proposed again when a corrected transcript moves it
  a little.
- **Why material, not edit state** (the table above planned edit state):
  candidates describe the recording, are found from material (transcripts),
  and a decision made in one edit should be seen in the others (WP21's
  "cut decisions travel between edits"). Each change is one material step,
  undone with Undo; applying a candidate is one step that changes the edit
  state (muted clips or a ripple) and the material (state `cut`) together.
  Open point for WP21: with several edits, `cut` says the candidate was
  accepted in *some* edit; whether this edit still plays it is derived
  (`heard` in `GET /api/candidates`), which is what an "offer cuts to other
  edits" view needs.
- **Bounded:** at most 1,000 records (`candidates.MAX_CANDIDATES`); the
  weakest open ones go first, decisions and marks stay. Measured: 1,000
  records pack to 19 KB in 8 ms per material revision.
- **Preserved:** records are updated field by field, so keys a newer kuulas
  adds to a record are kept, as are unknown root keys.

*Version and `min_reader`.* `min_reader` does not rise: the key is optional,
absent until the first candidate exists (old projects stay byte-identical),
and a reader that does not know it keeps it (roots are updated key by key)
and plays the project exactly as this version does, because a candidate
changes no audio until it is applied, and applying writes ordinary muted
clips or a ripple into the edit state. Such a reader only does not show the
candidates. By the "additive change" rule below, `version` should rise to 4
with a migration that rewrites nothing; that is left to the integrator,
since it touches `package.VERSION`, `db.SCHEMA_VERSION` and the migration
table that other work packages also bump.

**As built (mono speech tracks).** The edit state gains an optional
`Track.mono` (boolean, default false): the track is mixed down to ONE channel
everywhere it is rendered, as (L+R)/2 so a centred voice keeps its level, then
pan and gain apply as for any mono track. The stems export writes it as a
1-channel file, and the loudness curve and Match loudness measure the mono
signal. The key is absent while false, so a track that never had it keeps its
bytes and its state hash. It is set with `set_track` (one undo step).
`min_reader` does not rise: a reader that does not know it keeps the key in
`Track.extra` and plays the track in stereo, which is audibly different from
the mono mix but loses nothing and writes the key back.

**As built (WP49 loudness targets).** The edit state gains an optional
`Track.target_lufs` (float, LUFS, -70 to 0): where the track should sit. Absent
means the role's default (speech and narration -19, music -23; the role is the
track `kind`), and a track that never had one keeps its bytes and its state
hash. It is set with `set_track` (one undo step, saved with the edit state).

*Version and `min_reader`.* `min_reader` does not rise and `version` does not
change. The target changes no sound: it is only the number "match loudness" and
the editor's loudness curve aim at. A reader that does not know it keeps the
key in `Track.extra` and writes it back (the unknown-field rule below), so
nothing is lost; it only shows no target line, and its "match loudness" uses
its own fixed level. The cost is a missing monitoring hint, never a wrong
mix, so refusing to open is not worth it.

**As built (clip groups).** A clip gains an optional `group` (a string id).
Clips sharing an id are selected, moved, cut and muted together; the grouping
itself is in the edit state, so it is one undo step (`group_clips`,
`ungroup_clips`) and a split keeps it on both halves. Absent means ungrouped,
and an ungrouped clip is written without the key, so old projects keep their
bytes and state hash. `merge_clips` joins touching pieces of one recording into
one clip (the first id, fade-in and name, the last fade-out); only clips of the
same group (or all ungrouped) join.

*Version and `min_reader`.* `min_reader` does not rise and `version` does not
change. A group changes no sound. A reader that does not know it keeps the key
in `Clip.extra`, writes it back, and treats the clips as ungrouped: they then
select and move one by one. The cost is a convenience, never a wrong mix.

**As built (WP78 transcript timing).** The material root gains an optional
`media_timing` (media id -> `"whisper"` or `"ctc-v1"`): how exact the word times of that
media's current transcript are (`ctc-v1`: starts corrected by the podcast aligner). It is set
in the same material step as the transcript it describes, so Undo takes both back together;
a transcript from another engine (local transcription) clears it; correcting a word keeps
it. The key is written only while some media has a marker, so a project that never used it
keeps its bytes and hashes. `Media.timing` (a string, `""` when none) is that marker as the
composed state shows it, like `person`, and `Media.to_dict` leaves it out when empty.

*Version and `min_reader`.* Neither changes. The marker changes no sound and no word. A
reader that does not know it keeps the root key (roots are updated key by key) and shows no
marker.

Loudness curves (`GET /api/loudness-curve`) are a cache, not project data:
`caches/analysis/<key>.json`, keyed on the media hashes and every field that
changes the sound (a rename or a new target changes no key). Algorithm
`loudness-curve@1`.


## Media

- Identity is `sha256` of the file bytes; the id is `m` + its first 12 hex
  characters. If two different files ever collide in those 12 characters,
  the import refuses with a clear error (the full hash is stored and checked).
- `storage`:
  - `linked`: the original is read in place, checked by size and mtime, and
    by hash when the mtime changed.
  - `working`: a FLAC in `media/`.
  - `excerpt`: a FLAC in `media/excerpts/`.
- A media row is inserted only after its file is complete and renamed. The
  row is the "import finished" marker; today's per-media JSON files go away.
- Missing linked media: the project opens; those clips draw as offline
  (hatched) and play silence. Resolution runs in the background and checks,
  in order, the package-relative path, series-relative path, configured user
  media folders, learned root rewrites, and paths previously seen in this
  project. File size is only a prefilter; every accepted candidate must match
  the stored SHA-256. A manual relink can teach a root rewrite for the other
  missing files. Media folders and rewrites are stored in the user's
  `kuulas/media.json`, not in the project.
- **Portable paths** (WP39): a linked row also stores its path relative to
  the package and to the series folder. Resolution tries relative paths,
  then the user's media folders (by hash), then remembered paths. One
  relink teaches a path rewrite that fixes the other missing files.

## Caches

`caches/<kind>/<key>.<ext>`, where `key` = sha256 of
`{inputs: [media sha256s or blob hashes], params, algorithm: "<name>@<version>"}`.
Bump the algorithm version whenever its code changes what it computes. A cache
whose key cannot be computed is not used (fail closed), and every recompute is
logged. `caches/` is excluded from archives and backups and may be deleted
at any time.

## Compatibility and migrations

- **Reader rules:**
  - `min_reader` above the reader's own version: refuse to open, with
    "made by a newer kuulas (X); update to open it". Never guess.
  - `version` above the reader's own: open normally and preserve what it
    does not understand.
- **Unknown keys:** every model dataclass gains `extra: dict` (default empty).
  `from_dict` puts unknown keys there and `to_dict` writes them back. Same
  for unknown columns' data in `extra` (media) and unknown tables, which are
  never dropped.
- **Migrations** are forward-only functions `migrate_N_to_N+1(db, folder)`.
  Before running any, kuulas copies `project.sqlite` to
  `backups/pre-migration-vN-YYYYMMDDTHHMMSSZ.sqlite` with SQLite's online
  backup API. Then it migrates in one transaction, then rewrites the manifest.
- **Additive change** (a new optional field with a default) raises
  `version` only. **Breaking change** (renaming, changing a unit, moving
  data) raises `min_reader` too.

## Backups

While the project is open and has unsaved-to-backup changes, every 10
minutes kuulas writes `backups/auto-YYYYMMDDTHHMMSSZ.sqlite` (UTC in the
name) with the online backup API. It never touches the live file.

Kept: the last 12, plus the last one of each day for 14 days. Media is not
backed up: it is immutable and content-addressed, and its originals live
where they were.

## Hindenburg round trip

Importing `.nhsx` (WP13) stores the source session XML in project
`extra["nhsx"]`, and the original `<File>`, `<Track>`, and `<Region>` XML
with the corresponding media, track, and clip under each object's
`extra["nhsx"]["source_xml"]`. This keeps attributes and child elements that
kuulas does not model for a future exporter. Hindenburg export is not
implemented yet.

## Portability

- **Copy as is:** copy the folder. Linked media outside it shows as missing
  on the other machine until relinked or consolidated.
- **Archive:** "Export archive" consolidates linked media into the copy
  (lossless FLAC, WP19), leaves out `caches/` and `backups/`, and writes a
  zip with no compression (FLAC is already compressed). The archive gets a
  new project id only if the owner chooses "as a new project".

## Measured sizes (2026-10-16, see WP29 for the script)

A heavily edited hour: 4 mono mics, 300 ripple cuts on all tracks, 1,204
clips, 600 automation points.

| | per step | 5,000 steps |
|---|---|---|
| whole state, zlib 6 | 22.7 KB | about 111 MB |
| sharing unchanged tracks (not chosen) | about 9 KB for a one-track edit; the same as whole for a ripple cut | about 45 MB if every edit touched one track |

Whole states are kept. They are simple, need no replay, and 111 MB for an
extreme session is acceptable. Content addressing makes undo, redo and
restore cycles free. Revisit if real projects exceed 500 MB (WP29 logs the
database size on open).

## Migration from today's layout (WP29)

Today: a folder with `project.sqlite` (tables `nodes`, `meta`, `transcripts`)
and `media/` (`<id>.json`, `<id>.flac`, `<id>.peaks.npy`, `seen.json`,
`originals/`). Migration v0 to v1:

1. Back up `project.sqlite` (pre-migration copy).
2. Create the new tables. Move each `nodes.state` into `blobs` by hash and
   set `nodes.edit = 'main'`; create `edits('main')`.
3. Move `media/<id>.json` into `media` rows and `seen.json` into
   `media_paths`.
4. Move transcripts into `transcript_revs` (convert frames at project rate
   to flicks) and build the first material rev: transcript pointers taken
   from the head state, and sync groups from the clips' `sync` and
   `sync_origin` fields (WP30 converts them).
5. Move `<id>.peaks.npy` into `caches/peaks/`.
6. Write `manifest.json` last. Its presence marks a v1 project.

Projects created before v1 exist only on developer machines, so the
migration needs a test fixture, not a field rollout.

## Owner decisions (also in ROADMAP.md)

1. **The package folder** `Name.kuulas` (recommended) or a single file.
2. **History retention:** decided 2026-10-16: **keep every step forever**.
   Disk space is not a concern; speed is. Thinning exists only as a safety
   valve if a measured performance budget fails (WP40).
3. **Interchange beyond Hindenburg:** add OpenTimelineIO export for other
   editors (Premiere, Resolve, Reaper through adapters)? Not needed for v1.
4. **Editing from two machines:** the lock (one file per machine in `locks/`) makes the second machine
   read-only. Is that enough, or do you need to hand a project over
   explicitly ("check out" to the other machine)?
