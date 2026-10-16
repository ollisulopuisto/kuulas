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
| Dropbox, Syncthing, backups | audio uploads once and never changes; only `project.sqlite` churns | a multi-GB file changes on every edit |
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
  lock.json            who has it open (absent when closed)
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

## lock.json

`{"host", "pid", "user", "opened_utc", "heartbeat_utc"}`, rewritten every
30 s while open.

On open, kuulas reads the lock. If it is fresh (heartbeat under 2 minutes
old) and belongs to another host or process, the project opens
**read-only** with a banner naming that host. A stale lock is taken over,
with a warning. Removed on close.

This exists because two machines writing the same `project.sqlite` through
a sync service corrupts it, and the owner works across a Mac and a Windows
PC.

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
| tracks, buses, master, layers, roles, tags | edit state | — |
| markers and cut candidates (WP18) | edit state | anchor in flicks on a recording clock; timeline markers in project frames |
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

  Never the lock, backups or caches.

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

Importing `.nhsx` (WP13) keeps every XML attribute and element kuulas does
not model in the `extra` of the matching object, under `extra["nhsx"]`.
Exporting writes them back. A session imported and exported without edits
must produce XML equal to the input after canonicalisation (test with the
nhsx fixtures).

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
4. **Editing from two machines:** the lock makes the second machine
   read-only. Is that enough, or do you need to hand a project over
   explicitly ("check out" to the other machine)?
