# Disk: what a project folder holds, and keeping backups small

Owner report (2026-10-20): a transcribed interview project, `05 diet woke
litteroitu.kuulas`, took 1.1 GB, with no recordings in it and 7 MB of media.

## Where the space went

| Part | Size | What it is |
|---|---|---|
| `backups/` | 862 MB | automatic copies of the history |
| `caches/` | 139 MB | peaks, onsets, analysis, renders: rebuildable, safe to delete |
| `project.sqlite` | 112 MB | the history: every step keeps the whole edit state |
| `media/` | 7 MB | working files and excerpts |
| `recordings/` | 0 | takes recorded in kuulas |

### The cause

Every automatic backup was a full, uncompressed copy of `project.sqlite`,
made every 10 minutes while there were changes. Retention was by count only:
the newest 12 plus the newest of each of the last 14 days, up to ~26 copies.
At 112 MB a copy that is up to ~3 GB for one project.

## Measured: what compresses

A synthetic `project.sqlite` built the way kuulas writes one (each history
step a zlib-6 JSON state blob, each a small change of the one before; 2,200
steps, 106.5 MB), compressed whole on an M1 Max, 2026-10-20
(`lzma`/`gzip` from the standard library):

| Method | Size | Ratio | Compress | Decompress |
|---|---|---|---|---|
| gzip 6 | 104.6 MB | 1.02x | 2.3 s | 0.1 s |
| gzip 9 | 104.6 MB | 1.02x | 2.3 s | 0.2 s |
| xz preset 1 | 17.5 MB | 6.1x | 3.4 s | 0.9 s |
| **xz preset 3** | **11.0 MB** | **9.7x** | **5.0 s** | **0.6 s** |
| xz preset 6 | 10.1 MB | 10.5x | 7.7 s | 0.6 s |

gzip gains nothing because each state is already deflated and its 32 KB
window cannot see the previous state. xz's 4 MiB window (preset 3) reaches
the neighbouring states, which are nearly the same. Preset 3 is the knee:
preset 6 saves 1 MB more for 2.7 s more. No new dependency.

The real history may compress somewhat less than the synthetic one (states
that differ more from step to step); not yet measured on the owner's file.

## What changed

docs/FORMAT.md "Backups" has the rules. In short:

- New automatic backups are stored as `auto-<stamp>.sqlite.xz`, compressed
  on a background thread that pauses while audio plays, verified by
  decompressing before the plain copy is deleted.
- Plain backups of older versions are compressed the same way when the
  project is opened for writing.
- A size budget (default 300 MB, `backup_budget_mb` in settings.json, 0 = no
  limit) on top of the count rules; the newest 2 and the newest of each of
  the last 3 days always stay.
- No backup when nothing changed since the last, or when the disk has less
  free than twice the database.
- File > Statistics, "Size": the project folder, media, recordings, history,
  backups (count and total), caches and linked recordings, each with a
  one-line hint. `kuulas info` also lists `recordings`.

For the owner's project the expectation is: backups from 862 MB to roughly
26 × 112 MB / 9.7 ≈ 300 MB, and then within the 300 MB budget.

## Not done: the history itself

`project.sqlite` stays 112 MB: each step stores the whole state (deduplicated
by content, zlib per blob). Compacting it (tier B: store a step as a delta
against its parent, or compress states in groups with a shared dictionary)
is a format change and a separate work package.
