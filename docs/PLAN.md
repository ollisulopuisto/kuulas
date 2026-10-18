# kuulas implementation plan

This is the build plan for kuulas. It is written for an implementer who has
not seen the conversation that produced it. Everything you need is either here
or in the files this plan points to. `ROADMAP.md` says *what* and *why*; this
file says *how*, in work packages (WP) that can be picked up one at a time.

Read first, in this order:

1. `ROADMAP.md`: the requirements (R1–R34) and what is out of scope.
2. This file: "Ground rules" and "Architecture", then your WP.
3. The source files your WP names. They are short and commented.

---

## Ground rules (every WP)

These are not suggestions. A WP is done only when all of them hold.

1. **Red-green TDD.** Write the tests listed in the WP first. Run them and
   watch them fail (`uv run pytest -q tests/test_x.py`). Then implement until
   they pass. Never weaken an existing test to make it pass; if a test is
   wrong, say why in the commit message.
2. **Keyboard first.** Any UI feature includes its key binding and command
   palette entry in the same WP (R10; see Triage).
   **Translated from the start (R39).** No user-facing text is written as a
   literal, in Python or in the UI: it is a message key with an English
   source string and a Finnish translation in the same commit (WP33).
3. **Everything green.** `uv run pytest -q` passes in full and
   `uv run ruff check .` reports nothing. For UI work, also
   `npx @biomejs/biome@2.2.4 check ui/` (see WP0).
4. **No skipped tests.** A test that needs ffmpeg or an audio device must not
   silently skip. Hardware tests (audio devices) live in `tests/hardware/`,
   are excluded from the default run by `testpaths`, and are run by hand.
5. **Pure edits.** Every change to the project goes through a function in
   `src/kuulas/ops.py` (pure: `Project -> Project`) or through a `Session`
   command that ends in one `History.commit`. Never mutate a `Project`.
   Dataclasses are frozen; use `dataclasses.replace`.
6. **Frames, not seconds.** All positions in the model are integer frames at
   `Project.rate` (48000). Convert at the edges only (UI display, file I/O,
   speechmix calls that take seconds).
7. **Do not reimplement the pipeline.** Speech detection, ducking, pan laws,
   loudness, mastering and the speech chain come from `speechmix` and `nhsx`
   (`../podcast/packages/`). If something you need is missing there, stop and
   write it down in `ROADMAP.md` under "Open questions"; do not copy code.
8. **Never lose work.** Nothing the user did may exist only in memory: edits
   commit to `History` before the API answers; recordings and imports write
   `.partial` files and rename when complete.
9. **Content identity.** Media is identified by SHA-256 (`MediaStore`), never by
   file name or path.
10. **Docs in the same commit.** Each WP commit updates `CHANGELOG.md` (CalVer
   heading `## [vYY.MM.DD.N] - YYYY-MM-DD`, written for the person shipping
   it), marks the WP done in this file (`Status:` line) and updates the
   matching row in `ROADMAP.md`.
11. **Comments say why**, with the measured number when a constant came from a
    measurement. Match the density of the existing modules.
12. **Commits are local.** Commit on `main` with a message that says what and
    why. Do not push; there is no remote yet.
13. **Fail soft, isolate, report.** A bad file or a bad device costs that
    file or a second of audio, never the session. Decoders run with
    timeouts; plug-in renders run in worker processes; the audio callback
    never raises; every failure is logged and shown with how to fix it.
    Each WP that reads files or talks to devices includes fault-injection
    tests (truncated or garbage files, a device that errors or vanishes, a
    full disk, a crashing plug-in).
14. **Snappy is a requirement.** The UI never waits for heavy work: heavy work
    is a background job, and edits show a provisional result at once. Budgets,
    enforced by tests on the heavy-hour fixture: an edit's round trip under
    50 ms; waveform redraw under 8 ms per frame; no audio underruns while 4
    imports and a transcription run; 60 fps scrolling; the same with a
    CPU-heavy background job running. Each WP states its budget.
15. **Compute once, keyed by content.** Anything derived from a recording
    (waveform overviews, level envelopes, onsets, transcripts, restoration
    renders) is tied to the *media*, not the timeline, so edits never
    invalidate it. In-memory caches share one size budget (default 2 GB,
    LRU, spilling to `caches/`).
16. **Remember in the right scope; a repeated dialog is a bug.** Settings are
    remembered per user, per project, per user-view of a project, or per
    dialog (WP35). The plain key runs an action with the remembered settings;
    ⌥ + the key opens the dialog. Safety states reset on open: group editing
    is on, recording is not armed.

The project owner's standing rules, which apply to every WP on top of the above:

- **Heavy, strict lint.** Ruff with the rule set in `pyproject.toml` and
  Biome's recommended set plus a11y, correctness and suspicious for `ui/`.
  Do not weaken either config to get green. If a rule does not fit, add a
  per-file ignore with a written reason. A bare `# noqa` or
  `biome-ignore` without a reason is not allowed.
- **CalVer** `vYY.MM.DD.N` for the version and the CHANGELOG headings; bump
  `pyproject.toml`'s version in the same commit.
- **CHANGELOG entries are written for the person shipping the release:** what
  changed for users or operators, not file names.
- **README, ROADMAP.md and git log agree** at the end of every WP: what is
  done, what is left, and anything untested or waiting on the owner.
- **Times carry their timezone.** Any absolute time the UI or a report shows
  is Helsinki time with the zone named (e.g. "19:45 Helsinki"); stored times
  are UTC.
- **Caches and skips are keyed on content**, never on names, paths or
  commit lineage: media by SHA-256, analysis results by the hash of their
  inputs and parameters. A cache that cannot prove its key fails closed:
  recompute, and log what was recomputed.
- **Prior art before building:** for the XL packages (WP16, WP23) and WP26,
  first spend an hour looking for existing libraries (PyPI, GitHub) that do
  the hard part, and write what you found and why you used it or not in the
  WP's commit message.
- **No secrets on command lines or in chat.** A secret goes into a file the
  owner edits (e.g. a `.env` that is gitignored); code reads it from there.
- **CI, once a remote exists:** pull requests run the fast subset (lint +
  unit tests), and `main` runs everything, including the slow and hardware-free
  integration tests. Never cut the main-branch run down to save time.
- **GPU work** (bulk transcription, WP9/Colab) may use Google Colab, but never
  send private audio through Google Drive; send it to the VM directly.

Commands:

```
uv sync                       # install (needs ../podcast checked out next to kuulas)
uv sync --extra transcribe    # + faster-whisper
uv run pytest -q              # tests
uv run ruff check .           # lint
uv run kuulas open <dir>      # run the app (after WP3)
```

---

## Architecture

```
 browser UI (ui/, plain JS modules, Canvas 2D)
        │  HTTP JSON (localhost only)
        ▼
 server.py (FastAPI) ── session.py (one open project)
                           ├── history.py   undo tree + crash safety (SQLite)
                           ├── media.py     content-addressed media, FLAC, links
                           ├── engine.py    playback (sounddevice) ─┐
                           ├── recorder.py  recording (WP12)        │
                           ├── jobs.py      background work         │
                           └── ops.py / analysis.py / transcript.py │
                                         │                          │
                                         └── mixer.py ◄─────────────┘
                                             (same mix for playback and export)
```

Decisions already made (do not reopen them in a WP):

| Decision | Choice | Why |
|---|---|---|
| Engine language | Python + numpy | speechmix is Python; one mixer for playback and export |
| Audio I/O | `sounddevice` (PortAudio): CoreAudio on Mac, WASAPI on Windows, ALSA on Linux | standard APIs only; the user asked for nothing fancy |
| UI | Browser page served by the app, plain ES modules, no framework, no build step | runs everywhere; a desktop wrapper comes later (WP15) |
| UI drawing | Canvas 2D for the timeline; DOM for headers, panels, transcript | thousands of clips draw fast on canvas; text UI stays accessible |
| UI lint | Biome, pinned (`@biomejs/biome@2.2.4`), `recommended` + a11y + correctness | strict linting is a user rule |
| Transport state | UI polls `GET /api/transport` every 50 ms while playing, else on demand | simplest thing that works locally |
| Project on disk | a folder `<name>.kuulas/` | see "Project folder" |
| Undo | `History` stores whole states; every edit is one node | see `history.py` docstring |

### Project folder

A package folder `Name.kuulas/`, specified in `docs/FORMAT.md` (layout,
schema, reader rules, lock, backups) and built by WP29:

```
Interview.kuulas/
  manifest.json         format identity; written at create and on upgrade only
  project.sqlite        all state: material, edits, history (WAL)
  lock.json             who has it open (absent when closed)
  media/                MediaStore: <id>.flac, excerpts/, originals/
  caches/               peaks/ onsets/ analysis/ render/ (rebuildable)
  backups/              automatic and pre-migration database copies
  recordings/           WP12
```

### What exists today (2026-10-16, 86 tests passing, 1 failing, 27 lint findings)

| Module | Contents |
|---|---|
| `model.py` | `Media`, `Clip`, `Track`, `Bus`, `SyncGroup`, `Project` (frozen dataclasses, JSON round-trip, unknown keys kept in `extra`; sync per media in flicks, WP30) |
| `package.py` | (WP29) `create`, `open_package`, manifest, lock, migrations, backups, `info` |
| `db.py`, `migrations.py`, `caches.py`, `clock.py`, `cli.py` | (WP29) v1 schema and blobs, UUIDv7 step ids; v0 to v1; cache keys; flicks and `check_rate` (WP30); `kuulas info` |
| `ops.py` | all edits; `OPS` whitelist; `apply(p, name, args)` |
| `history.py` | `History(path, edit=)`: `commit(label, state, coalesce, op=, context=, material=)`, `undo`, `redo`, `goto`, `nodes`, `create_edit`, `checkpoint`, `add_transcript`, `transcript`, `transcripts` (WP29: material apart from edit state) |
| `curves.py` | breakpoint curves in dB |
| `mixer.py` | `mix(project, store, first, count) -> (2, count) float32` |
| `media.py` | `MediaStore`: `import_file(s)`, `read`, `peaks`, `find`, `seen_paths`, `missing`, `relink`, `consolidate`, BWF time reference; metadata as `media` rows, peaks in `caches/` (WP29) |
| `analysis.py` | `silence_ranges`, `auto_silence`, `automix` (speechmix grid + duck masks) |
| `transcript.py` | `timeline_words`, `cut_range` |
| `transcribe.py` | `parse` (JSON), `from_segments`, `local` (faster-whisper) |

The UI, server, engine, session, jobs, export and recorder do not exist yet.

---

## Triage: build order, size, and who should build it

Size: **S** ≈ a day, **M** ≈ 2–4 days, **L** ≈ a week, **XL** > a week.
**Model** says which model builds the WP:

- **Haiku 5.5:** small and mechanical. The spec and the tests leave
  nothing to decide. Run it, check that tests and lint are green, merge.
- **Sonnet 5.5:** most of the work. Medium-sized packages with clear
  specs, including all the UI. Review the diff before merging.
- **Opus 5.5:** the hard ones: real-time audio, hardware, schema changes,
  algorithms with judgement calls (drift, time-stretch), and the anchoring
  model other WPs build on. Review closely, and run the hardware tests by
  hand.

Also have **Opus 5.5 review each phase's exit** (the phase's exit test plus
a read of every diff in that phase) before the next phase starts. A simpler
model's mistake caught at a phase boundary costs a day; caught three
phases later, it costs a rewrite.

### Milestone M1 — first playable build (the owner's first target)

Run `kuulas open`, import files, hear them, edit by keyboard (split, cut on
all tracks, trim, nudge, mute), undo, and export WAV or **MP3**. The steps on
the way, in order: WP33a, WP29, WP30, WP1 (all done), then WP2 (engine) in
parallel with WP34 (import hardening) and WP36 (caches), then WP3, WP33b, WP4,
WP5, WP19a (editing in sync), WP35 (remembered settings), WP11 (export,
in parallel with WP4). Everything else in phase 1 follows
M1. Estimate on 2026-10-16: about 10–12 hours of agent work in sequence,
plus the owner's listening test of WP2 on the Mac.

### Phase 0 — Foundation (nothing works without it)

| Order | WP | Size | Hard part | Model |
|---|---|---|---|---|
| 1 | WP0 baseline, lint, first commit (done) | S | none | Haiku 5.5 |
| 2 | WP24.1 solo rules (done) | S | none | Haiku 5.5 |
| 3 | **★ WP33a i18n in Python: catalogs, messages, speechmix translator (R39)** | S | never raise on error paths; convert existing literals | Haiku 5.5 |
| 4 | **★ WP29 project format v1 (R35, docs/FORMAT.md)** | L | material vs edit state, migrations, lock | **Opus 5.5** |
| 5 | **★ WP30 recording clock in flicks, sync per media (R35)** | M | changes the sync model without changing behaviour | **Opus 5.5** |
| 6 | WP1 session | M | import as one sync group, one commit | Sonnet 5.5 |
| 7 | **WP34 import hardening (fail soft)** | M | timeouts, partial imports, broken-file fixtures | Sonnet 5.5 |
| 8 | **WP36 caches per recording (peak pyramid, envelopes)** | M | edits never invalidate media caches | Sonnet 5.5 |
| 9 | WP2 playback engine | M | glitch-free real-time callback, prefetch | **Opus 5.5** |
| 10 | WP3 HTTP API + CLI | M | none | Sonnet 5.5 |

### Phase 1 — MVP: an editor you can actually use

Exit test: import a 2-mic interview, transcribe it, listen through at 1.5×,
cut by text and by keyboard, Tab through transients, automix with a real-time
plugin on a voice, undo anything, export a mastered file.

| Order | WP | Size | Hard part | Model |
|---|---|---|---|---|
| 11 | **★ WP33b i18n in the UI (R39)** | M | Intl formatting, key names, literal-text check | Sonnet 5.5 |
| 12 | **WP41 people, interviews, who speaks (data model)** | M | person on every word from the first transcript | Sonnet 5.5 |
| 13 | WP4 UI shell + timeline | L | canvas drawing, zoom, hit-testing | Sonnet 5.5 |
| 14 | **★ WP5 keymap + palette (R10)** | M | many bindings, collision test | Sonnet 5.5 |
| 15 | **★ WP19a edit groups: what an edit touches (M1)** | M | target × time-shifting rule, partners by recording time | Sonnet 5.5 |
| 16 | **WP35 remembered settings, quick actions, view memory** | M | scopes; a repeated dialog is a bug | Sonnet 5.5 |
| 17 | **★ WP8 history panel + stateful undo (R29)** | M | ledger restore, context restore, change flash | Sonnet 5.5 |
| 18 | **★ WP22 track tags + ducking (R30)** | S | music-bed curve from nhsx | Sonnet 5.5 |
| 19 | **★ WP26 fast listening + JKL (R33)** | L | streaming time-stretch, JKL state machine | **Opus 5.5** |
| 20 | **★ WP19i tab to transient / word (R26i)** | M | onset detection; word mode waits for WP7 | Sonnet 5.5 |
| 21 | WP6 mouse editing | M | drag state machine | Sonnet 5.5 |
| 22 | WP9 jobs + local transcription | M | parallel faster-whisper | Sonnet 5.5 |
| 23 | WP7 transcript panel | M | selection → word indices | Sonnet 5.5 |
| 24 | **★ WP23a FX layers: real-time tier + analyse-then-live tier (R30)** | L | real-time plugins in the callback, latency compensation, CPU meter | **Opus 5.5** |
| 25 | WP11 export + mastering | M | parallel ordered render | Sonnet 5.5 |

### Phase 2 — The editing loop (what makes it better than Hindenburg)

| Order | WP | Size | Hard part | Model |
|---|---|---|---|---|
| 26 | WP28 focus mode | M | lane layout, speaker focus, solo restore | Sonnet 5.5 |
| 27 | WP43 narration placeholders | M | estimated length, replace with a take | Sonnet 5.5 |
| 28 | WP18 cut candidates | M | recording-clock anchoring (later WPs reuse it) | **Opus 5.5** |
| 29 | WP19f spot | S | parsing | Haiku 5.5 |
| 30 | WP24.2 A/B | M | edit A/B position mapping, level match | Sonnet 5.5 |
| 31 | WP21 several edits (versions) | L | history schema migration, offer_cuts | **Opus 5.5** |
| 32 | WP40 long history stays fast | M | paged panel, incremental backups, thinning valve | Sonnet 5.5 |
| 33 | WP31 changes view + checkpoints | M | recording-range diff | Sonnet 5.5 |
| 34 | WP32 review round trip: suggest mode, hand-off, merge | L | diverged copies become suggestions | **Opus 5.5** |
| 35 | WP20 paste without bloat | M | excerpt media keeping recorded time | Sonnet 5.5 |
| 36 | WP39 portable projects: different paths on every machine | M | resolution order, learned path rewrites | Sonnet 5.5 |
| 37 | WP37 usage extractor | S | recording ranges with audibility | Sonnet 5.5 |
| 38 | WP19c roles, stems, match loudness | M | stems sum test | Sonnet 5.5 |
| 39 | WP19d remappable keys + macros | M | macro = one undo step | Sonnet 5.5 |
| 40 | WP19b connected clips | M | reflow after every edit | Sonnet 5.5 |
| 41 | WP19h regions + batch export, chapters | S | none | Haiku 5.5 |
| 42 | WP19g skimming | S | grain throttling | Sonnet 5.5 |
| 43 | WP19e alternative takes | L | ripple on take length change | Sonnet 5.5 |

### Phase 3 — Pipeline depth

| Order | WP | Size | Hard part | Model |
|---|---|---|---|---|
| 44 | WP14 parallel analysis (done) | S | none | Haiku 5.5 |
| 45 | WP10 voice chain variants | M | variants, chain settings | Sonnet 5.5 |
| 46 | WP25 music report | S | heard-duration rules | Haiku 5.5 |
| 47 | WP13 Hindenburg import | M | `.nhsx` word clock | Sonnet 5.5 |
| 48 | WP23b FX layers: render tier, export waits, freeze on overload | L | background render, overload policy | **Opus 5.5** |

### Phase 4 — Recording and alignment

| Order | WP | Size | Hard part | Model |
|---|---|---|---|---|
| 49 | WP12 recording, foolproof mode, live logging | L | hardware, crash recovery, sleep prevention | **Opus 5.5** |
| 50 | WP17 clip bin | M | Space and in/out rules | Sonnet 5.5 |
| 51 | WP16 align by sound | **XL** | drift and dropout detection | **Opus 5.5** |

### Phase 5 — Late (series features here: owner, 2026-10-16)

| Order | WP | Size | Hard part | Model |
|---|---|---|---|---|
| 52 | WP27 settings + rate change | L | converts every position kind; do it when the model has stopped growing | **Opus 5.5** |
| 53 | WP38 series: reuse across episodes | L | per-project usage files, badges, series view | Sonnet 5.5 |
| 54 | WP42 bits and index-card view (Scrivener-style) | L | outline to timeline, person view | Sonnet 5.5 |
| 55 | WP15 desktop wrapper | M | packaging | Sonnet 5.5 |

**Easiest wins:** WP0, WP24.1, WP22, WP19a, WP19f, WP19h, WP14, WP25.
**Hardest, highest risk:** WP23 (real-time FX), WP16 (align by sound),
WP12 (recording), WP26 (streaming time-stretch), WP27 (rate change), WP21
(schema migration), WP2 (real-time engine). Each goes to Opus 5.5, with a
review. Do a spike first where the plan says "test it" on hardware.

**★ = build first** (owner, 2026-10-16): R35 the project format, R39 i18n, R10
keyboard, R29 trustworthy undo, R30 track tags, ducking and real-time FX,
R33 fast listening, R26i Tab to transient. R35 above all: every later WP
writes data in that format.

**Keyboard first (R10).** WP5 comes straight after the UI shell, before
any other UI work. From then on **every UI WP ships its keys in the same
commit**: a feature without its keyboard binding and palette entry is not
done, and the keymap collision test must pass. The editor must be fully
usable without a mouse at every milestone.

**Why this order:** the MVP proves the core loop before any power feature.
WP18's anchoring comes early because WP19b, WP21 and WP12's live log reuse
it. WP27 comes last because every new position kind added before it is one
more thing it must convert.

---

## Work packages

Dependency order. WPs on the same line can run in parallel.

```
WP0
WP1
WP2  WP9  WP10  WP11  WP13  WP14
WP3
WP4
WP5  WP6  WP7  WP8
WP18 (needs WP1, WP4, WP5)   WP19a–i (needs WP1, WP4, WP5)   WP20 (needs WP1, WP4)   WP21 (needs WP1, WP4, WP8)   WP22 (right after WP4)   WP23 (needs WP2, WP9)   WP24.1 (right after WP0)   WP24.2 (needs WP4, WP21, WP23)   WP25 (needs WP11, WP21, WP22)   WP26 (needs WP2, WP5)   WP27 (needs WP2, WP9, WP21)
WP12 (needs WP1, WP2)  WP16 (needs WP1, WP9)  WP17 (after WP5–WP8)
WP15 (last)
```

---

### WP0 — Baseline: green, linted, committed

Status: done in v26.10.16.1. Tests 87 passing; `ruff check` clean; Biome clean.
The video-audio threshold was lowered from 0.1 to 0.05 because AAC coding
lowers a 0.125 tone to 0.09–0.10 (ffmpeg's own decode agrees); see the commit.

1. Add `.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`,
   `*.kuulas/`, `node_modules/`.
2. `tests/test_media.py::test_audio_is_taken_from_video` fails because stereo
   upmix of the lavfi tone peaks at about 0.088. Change the threshold from
   `> 0.1` to `> 0.05`. That is the whole fix; the decoder is correct.
3. Fix all `uv run ruff check .` findings:
   - `PLC0415` (import inside function): move the import to the top of the
     module, **except** `faster_whisper` in `transcribe.local` (optional extra).
     For that one add a `per-file-ignores` entry for `src/kuulas/transcribe.py`
     with a comment saying why. Import `speechmix.binaries` at the top of
     `media.py`.
   - `PLW2901` (loop variable reassigned) in `ops.py`: assign to a new name.
   - `E501`: wrap lines.
   - tests: use `next(...)` instead of `[...][0]`, `itertools.pairwise`, drop
     unused imports, split `assert a and b`.
4. Create `CHANGELOG.md` with `## [v26.10.16.1] - 2026-10-16` describing the
   core (model, edits, history, mixer, media store, analysis, transcript, sync
   groups) in user terms.
5. Write `README.md`: what kuulas is (two sentences), how to run the tests,
   that it needs `../podcast` next to it, and links to `ROADMAP.md` and this file.
6. Add `CLAUDE.md` at the repo root that says: read `docs/PLAN.md` ground rules
   before changing anything.
7. Add `ui/biome.json` (create `ui/` now):
   ```json
   {
     "$schema": "https://biomejs.dev/schemas/2.2.4/schema.json",
     "linter": { "enabled": true, "rules": { "recommended": true,
       "a11y": { "recommended": true }, "correctness": { "recommended": true },
       "suspicious": { "recommended": true } } },
     "formatter": { "enabled": true, "indentStyle": "space", "lineWidth": 100 }
   }
   ```
8. Commit everything as the first commit.

Acceptance: `uv run pytest -q` all green, `uv run ruff check .` clean,
`git log` shows one commit.

---

### WP1 — Session: one open project

Status: done in v26.10.16.7. Needs WP0. Adapted to WP29/WP30: no
`ops.add_media`/`ops.set_transcript` (media rows and transcript revisions live
in the material; `state` already shows imported media), history steps are UUID
strings (`goto(node: str)`), BWF times and sync origins are flicks. Solo/mute
coalescing (WP24.1) is in `Session.edit`. Not built here: `Session.edit_target`
(WP19a).

New file `src/kuulas/session.py`. A `Session` owns everything for one project
folder, and every API call goes through it. It is the only place that
combines `History`, `MediaStore` and `ops`.

```python
class Session:
    def __init__(self, folder: Path, rate: int = 48000): ...
        # opens or creates a Name.kuulas package (docs/FORMAT.md, WP29):
        # manifest, lock, project.sqlite, media/, caches/
    state: Project                      # property -> history.state
    history: History
    store: MediaStore
    lock: threading.RLock               # every public method holds it

    def edit(self, name: str, args: dict, label: str | None = None,
             coalesce: str | None = None) -> Project
        # ops.apply + history.commit; label defaults to name
    def command(self, name: str, args: dict) -> Project
        # edits that need the store: see COMMANDS below
    def undo(self) -> bool; def redo(self) -> bool; def goto(self, node: int) -> None
    def import_media(self, paths: list[str], copy: bool = False,
                     track_per_file: bool = True) -> Project
        # store.import_files (parallel), ops.add_media for new ones,
        # one new track per file with one clip at 0; ONE commit labelled
        # "import N files". Stereo media -> track kind "music", mono -> "speech".
        # Files imported together are IN SYNC BY DEFAULT: their clips are
        # placed by BWF time reference (relative to the earliest; files
        # without one start at 0) and marked as one sync group
        # (ops.mark_in_sync, basis="files", main = first file). A file that
        # does not belong (a Zoom or phone recording) is aligned by hand and
        # added with "mark in sync"; see "Sync workflow" below.
    def transcripts(self) -> dict[str, list[dict]]
        # media id -> words, via state.transcripts revs, cached by rev
    def set_transcript(self, media_id: str, words: list[dict], label: str) -> Project
        # history.add_transcript + ops.set_transcript, one commit
    def timeline_words(self) -> list[dict]
    def subscribe(self, fn: Callable[[Project], None]) -> None
        # called after every state change (engine uses it)
```

`COMMANDS` (dict name -> function in `session.py`, each one commit):

| name | args | does |
|---|---|---|
| `auto_silence` | `{track_ids?: [..]}` | `analysis.auto_silence` (only given speech tracks if set) |
| `automix` | `{depth_db?: float}` | `analysis.automix` |
| `cut_words` | `{indices: [int]}` into `timeline_words()` | `transcript.cut_range` then `ops.ripple_delete` on all tracks; label `cut "<first words>"` |
| `relink` | `{folder: str}` | `store.relink`; no commit (no state change) |
| `consolidate` | `{}` | `store.consolidate`; no commit |

Tests first (`tests/test_session.py`), using small WAVs written with
`soundfile` in `tmp_path`:

- `test_new_session_creates_the_folder_layout`
- `test_edit_commits_one_undo_step`
- `test_session_reopens_at_the_last_edit` (close without `close()`, reopen)
- `test_import_makes_one_track_per_file_in_one_undo_step`
- `test_import_classifies_mono_as_speech_and_stereo_as_music`
- `test_reimporting_the_same_file_adds_no_media`
- `test_files_imported_together_form_one_sync_group`
- `test_bwf_time_references_place_clips_relative_to_the_earliest`
- `test_a_single_imported_file_gets_no_sync_group`
- `test_cut_words_ripples_every_track` (import two files, attach a transcript
  with `set_transcript`, cut word 1, check both tracks lost the same range)
- `test_set_transcript_is_undoable`
- `test_subscribers_see_every_change_including_undo`
- `test_unknown_command_raises_edit_error`

Acceptance: tests green; `Session` used by nothing else yet.

---

### WP2 — Playback engine

Status: done in v26.10.16.8. 237 tests pass (37 new: `tests/test_engine.py`).
Default buffer 1024 frames, as the "Buffer size" rule says (the signature
below said 2048). Output resampling uses soxr (new dependency). Not built
here: following a *default-output switch* while the old device still works
(PortAudio cannot see it; the next play after 30 s idle, or any stream
failure, picks up the new default), the "rebuild damaged media from the
original" action (status lists `damaged`; the rebuild belongs to the media
store, WP34/WP36), freezing a real-time layer when late (WP23a), prefetch
priority over background jobs (no job runner yet; WP9). `scrub` is a seek
while playing and a 60 ms burst when stopped, until WP26.
Hardware test `tests/hardware/test_play.py` not yet run on Mac or Windows. Rebuilding a damaged file is a Session command since v26.10.17.2, but clearing the engine's damaged mark afterwards is open: it needs an `Engine.clear_damaged(media_id)` (a decision about the engine's narrow surface) and a call from the server. Finding on the default-output switch (agy, 2026-10-17): PortAudio and sounddevice have no device-change notification and cache the default device at initialisation, so a switch is only seen after the stream is closed and PortAudio re-initialised. Lowering `IDLE_CLOSE_S` from 30 s to about 5 s would pick up a switch at the next play after idle, at the cost of a slightly slower first play after idle; instant detection needs native listeners (CoreAudio, Windows Core Audio, PulseAudio) and belongs with the desktop wrapper (WP15). No code change yet.

New file `src/kuulas/engine.py`.

```python
class Engine:
    def __init__(self, session: Session, blocksize: int = 2048, device=None): ...
    def play(self, at: int | None = None, until: int | None = None) -> None
    def stop(self) -> None
    def seek(self, frame: int) -> None
    def status(self) -> dict    # {"playing": bool, "position": int, "until": int|None}
    def close(self) -> None
```

Rules:

- One `sounddevice.OutputStream(samplerate=rate, channels=2, dtype="float32",
  blocksize=blocksize, latency="high", callback=...)`, opened on first `play`.
- The callback calls `mixer.mix(self._project, store, pos, frames)` and writes
  `.T` into `outdata`. `self._project` is replaced by the `subscribe` hook
  (a plain attribute assignment is atomic in CPython). The callback **never**
  takes `session.lock`.
- `until`: stop at that frame (play selection). At the end of the project,
  stop and leave the playhead at the end.
- Prefetch: a daemon thread wakes every 250 ms while playing and calls
  `store.read` for every clip intersecting `[pos, pos + 5 s)` so FLAC chunks
  are decoded before the audio thread needs them.
- Keep `mix_block` testable without hardware: put the per-block logic in
  `Engine._render(frames) -> np.ndarray` and test that.
- Missing audio device: `play` raises `EngineError("no output device")`, and
  the API reports it; the app still opens.
- **Display follows the ear.** The position reported to the UI is the frame
  being *heard*: the engine's render position minus the device's output
  latency (`stream.latency`, in frames). The playhead, transcript highlight
  and meters use that position, so they do not run 20–45 ms ahead of the
  sound.
- **Buffer size:** 1024 frames (about 21 ms) by default; 2048 when the CPU
  meter (WP23a) shows sustained load over 60 %.
- **The door to a native engine stays open** (decided 2026-10-16): nothing
  outside `engine.py` may assume playback is done in Python. The engine's
  public surface is `set_project`, `play`, `stop`, `seek`, `scrub`, `status`,
  `levels` (and `record` in WP12), plain data in and out. If the Python
  engine fails WP23a, WP26 or WP12 on glitches or latency, it is replaced by
  a JUCE engine built as a Python extension (the way pedalboard is built),
  behind the same surface. Not Tracktion: its own edit model and undo would
  fight ours.
- **Golden renders:** `tests/golden/` holds small fixture projects (pan,
  fades, crossfades, envelopes, automation, buses, solo/mute) with reference
  output from `mixer.mix`, as 32-bit float WAV plus its SHA-256. Any engine,
  Python or native, must reproduce them within 1e-6. A change to the mixer
  that changes a golden file must say why in its commit.

Tests (`tests/test_engine.py`, no audio device, monkeypatch
`sounddevice.OutputStream` with a fake that records calls):

- `test_render_advances_the_position`
- `test_render_stops_at_until_and_pads_with_silence`
- `test_edit_during_playback_is_heard_in_the_next_block`
- `test_render_never_takes_the_session_lock` (hold the lock in another
  thread; `_render` must return)
- `test_seek_while_playing_moves_the_position`
- `test_reported_position_subtracts_output_latency`
- `test_golden_renders_match` (and a script to regenerate them, which
  refuses to run without `--i-changed-the-mixer`)

**Fault tolerance (ground rule 13):**
- The callback catches everything: a failing block plays silence, is
  counted, and is reported; the stream keeps running.
- **Device changes** (headphones unplugged, default output switched,
  Bluetooth dropping, stream finished or errored): pause, reopen the new
  default device, and tell the user. Never a dead stream with the play
  state still on.
- **Device cannot run at the project rate:** resample on output and say so.
- **Late blocks:** first raise the buffer to 2048, then freeze the
  heaviest real-time layer (WP23a), and show "playback is struggling";
  never stutter silently.
- **Damaged cache chunk** (a decode error inside `MediaStore.read`): that
  stretch plays silence, and the media is marked damaged with an offer to
  rebuild it from the original (hash-checked).
- **Watchdog:** if the callback has not run for 1 s while playing, restart
  the stream.
- **Priority:** the audio thread never waits on a lock that a non-audio
  thread holds for long; prefetch runs above every background job.

Fault-injection tests: a fake stream that raises in the callback, reports
`output_underflow`, finishes unexpectedly, or refuses the rate;
`MediaStore.read` raising for one chunk.

Hardware smoke test `tests/hardware/test_play.py`: plays 1 s of a sine through
the default device; run by hand on Mac and Windows.

---

### WP3 — HTTP API and CLI

Status: done in v26.10.16.11. 360 tests pass (41 new: `tests/test_server.py`).
Where the table below and the code disagreed, the code won: step ids are
strings (UUIDv7), not ints; waveforms are served as the WP36 tiles
`GET /api/peaks/{media}/{level}/{tile}` (ETag, immutable cache, 304), not
`?per=N`; errors are `messages.error_body` (`{"error": {key, params, text}}`),
not a bare message. `POST /api/restore` adds a step (`Session.restore`,
`History.restore`) and answers with `"context": null` until WP8 stores UI
context. `POST /api/import` and `/api/upload` also return `report`, one entry
per file; when no file could be imported the answer is a 500 carrying that
report. `POST /api/transport` also takes `scrub`. Edit round trip measured
at 14 ms median (37 ms worst) on the heavy-hour fixture, through the
TestClient. Not built: `GET /api/jobs`, `POST /api/export` (WP9, WP11). Not
tried in a real browser. Needs WP1, WP2.

New files `src/kuulas/server.py`, `src/kuulas/cli.py`.

`kuulas open <folder>` (creates it if missing): starts uvicorn on
`127.0.0.1:<free port>`, serves `ui/` as static files at `/`, opens the
default browser. Bind to 127.0.0.1 only.

Endpoints (all JSON; errors are `{"error": "<message>"}` with status 400 for
`EditError`, 404 for unknown ids, 500 otherwise):

| Method, path | Body | Returns |
|---|---|---|
| `GET /api/state` | | `{"project": Project.to_dict(), "head": int, "can_undo": bool, "can_redo": bool, "missing": [media ids]}` |
| `POST /api/edit` | `{"op", "args", "label"?, "coalesce"?}` | same as state |
| `POST /api/command` | `{"name", "args"}` | same as state |
| `POST /api/undo`, `/api/redo` | | same as state |
| `POST /api/restore` | `{"node": int}` | same as state, plus `context` (see WP8) |
| `GET /api/history` | | `{"nodes": [...], "head": int}` |
| `POST /api/import` | `{"paths": [str], "copy": bool}` | state |
| `POST /api/upload` | multipart files | state (saved to `<project>/uploads/` then imported with `copy=False`) |
| `GET /api/peaks/{media}?per=N` | | `application/octet-stream`, float32 little-endian, `[min,max]` pairs; header `X-Peak-Frames: <per actually used>` |
| `GET /api/words` | | `{"words": session.timeline_words()}` |
| `POST /api/transcript/{media}` | word JSON in any shape `transcribe.parse` accepts | state |
| `PUT /api/word` | `{"media", "index", "w"}` | state (corrects one word's text: new transcript revision) |
| `GET /api/transport` | | `engine.status()` |
| `WS /api/live` | | **push channel** (replaces polling): playback position (heard frame) at display rate while playing, job progress, state-changed notices with the new head id, device and engine warnings. The UI keeps one connection and reconnects with backoff, showing "reconnecting…" |
| `POST /api/transport` | `{"action": "play"|"stop"|"seek", "at"?, "until"?}` | `engine.status()` |
| `GET /api/jobs` | | WP9 |
| `POST /api/export` | WP11 | |

The server converts nothing: frames stay frames.

Tests (`tests/test_server.py`, FastAPI `TestClient`, engine replaced by a fake):
one test per endpoint for the happy path, plus
`test_edit_error_is_400_with_message`, `test_upload_imports_the_file`,
`test_peaks_are_binary_float_pairs`, `test_server_binds_localhost_only`
(inspect the uvicorn config the CLI builds).

---

### WP4 — UI shell and timeline

Visual target: `docs/ui-sketches.html` (open it in a browser). The sketches
fix layout and behaviour, not final styling.

Status: functional baseline done in v26.10.17.7 (waveform lanes in a worker, headers, inspector, zoom and Z, overview, follow modes, F6 focus, import, live channel). NOT yet verified: Space playing real audio, playhead under live position messages, drag-and-drop and file picker in a browser, light mode. The visual and interaction design was done by Opus on 2026-10-17 and merged in v26.10.17.8: read `docs/design/GUI-DESIGN.md` (spec, visual grammar, component inventory, how to add a signal or a theme) and look at `docs/design/prototype/index.html` before touching `ui/`. Needs WP3.

Files under `ui/`: `index.html`, `style.css`, `app.js` (entry), `api.js`,
`store.js` (client state), `timeline.js` (canvas), `tracks.js` (headers and
mixer strips), `inspector.js`, `format.js` (frames ↔ `h:mm:ss.mmm`).

Layout (one screen, no page scroll):

```
┌ toolbar: transport · time · project name ─────────────────────────────┐
├ track headers ┬ timeline canvas (ruler, lanes, clips, playhead) ──────┤
│ name M S bus  │                                                        │
│ gain pan      │                                                        │
├───────────────┴───────────────────────────┬────────────────────────────┤
│ transcript panel (WP7)                    │ inspector / history (WP8)  │
└───────────────────────────────────────────┴────────────────────────────┘
```

Client state (`store.js`), single object, re-render on change:
`{project, head, canUndo, canRedo, words, selection: Set<clipId>,
focusTrack: trackId, playhead: frame, inPoint, outPoint, zoom (frames per
pixel), scroll (frame at left edge), playing}`. Selection, focus, in/out,
zoom and scroll are **UI state**: they are not edits and are not in history.

Timeline drawing (`timeline.js`), all from state:

- Ruler with time labels that adapt to zoom.
- One lane per track; height 48 px (Mod+Shift+=/- changes it, 24–160).
- **Half waveforms, as Hindenburg draws them** (the default; it saves half
  the height): each column draws `max(|min|, |max|)` from `/api/peaks` as
  a bar rising from the lane's bottom edge. View menu (or Alt+Mod+W) switches
  to classic full waveforms (min/max around the centre line). Draw speech
  with a dB-shaped vertical scale (−48 dBFS at the bottom, 0 at the top) as
  an option, so quiet speech stays visible at small heights. Pure function
  `waveformColumns(peaks, mode, scale, height)`, tested.
- Clips: rectangle, name of media, waveform from `/api/peaks` (request
  `per = zoom` rounded to a power of two of 256; cache per media and `per`).
- Muted clips drawn with 35 % opacity and a hatch; selected clips with a 2 px
  accent outline; crossfade regions as a darker triangle pair.
- Clip gain: a horizontal line inside the clip at its `gain_db`; envelope
  points as 6 px dots joined by lines.
- Track automation (ducking): a thin line in the lower third of the lane.
- Playhead: 1 px vertical line; in/out range shaded.
- Use `devicePixelRatio`; redraw with `requestAnimationFrame` only when state
  changed or while playing.

Track headers: name (double-click to rename), M, S buttons, bus `<select>`,
gain slider (−60..+12 dB) and pan slider (−100..100). Slider drags send
`set_track` with `coalesce: "track-gain-<id>"` so a drag is one undo step.
Buses appear as extra header rows below the tracks with the same controls.

Inspector (selected clip, single selection): gain, pan, fade in/out (ms),
muted, sync group; edits use `set_clip` with coalesce keys.

**Navigation (decided with the owner, 2026-10-16):**

- **Three zooms, kept apart:**
  - time (horizontal): = / - step through snap levels named by time on
    screen: whole edit, 30 min, 10 min, 5 min, 2 min, 1 min, 30 s, 10 s,
    5 s, 2 s, 1 s, 500 ms, 100 ms, samples. The toolbar shows "Close · 2 s".
    Pinch and Mod + wheel zoom continuously and settle on a level when
    released within 8 %;
  - waveform height: Alt + wheel over a lane, or Alt+= / Alt+-, display only,
    with a "×4" label while not 1:1;
  - lane height: Shift+= / Shift+- for all, drag a lane edge for one.
- **Z toggles a close view and a wide view**, each remembered (level and,
  for the wide view, position). = / - adjust whichever view is current.
  Shift+Z fits the selection or in→out, or the whole edit when nothing is
  selected. Alt+Z / Shift+Alt+Z step back and forward through recent views
  (view history, never undo history).
- **Zoom anchor order:** the last edit point if the last action was an edit
  (zoom out after finessing a cut keeps that cut in place on screen), else
  the pointer over the timeline, else the playhead. The anchor does not move
  on screen.
- **Scrolling:** a trackpad scrolls naturally in both directions. A mouse
  wheel scrolls time when all lanes fit, otherwise lanes; Shift + wheel
  always scrolls time.
- **Overview strip** above the timeline: the whole edit with a box for the
  visible part; drag or click to move.
- **Following the playhead:** page or continuous, toggled with one key.
  Scrolling by hand while playing pauses following until the key is
  pressed or the playhead is back in view. The transcript follows the same view.
- **Keyboard focus:** the timeline is home and Esc always returns there;
  F6 / Shift+F6 cycle timeline → transcript → inspector → history; a click
  focuses a panel; the focused panel's header shows an accent edge; focus
  stays where an action happened; Space always plays/stops except inside a
  text field; dialogs and the palette return focus where it was.
  Vocabulary: **keyboard focus** (which panel), **current track** (the ↑/↓
  cursor, previously called "focused track"), **focus mode** (F, WP28).

**Performance (ground rule 14):** waveforms are drawn in a Web Worker on an
`OffscreenCanvas`, from binary peak tiles (WP36) cached by content hash, so the
browser caches them too; the transcript, history and candidate lists are
virtualized; no main-thread task over 16 ms, watched by a long-task monitor
in development; drags show a provisional result at once.

Tests: UI logic that is not drawing goes into pure functions in
`format.js` and `store.js`; test them with `node --test ui/tests/` (Node's
built-in runner, no dependencies). At minimum: frame/time formatting, zoom
math (frame ↔ x), hit testing (x,y → clip id, edge, envelope point).

Acceptance: open a folder with two imported WAVs, see both lanes with
waveforms, play with Space, see the playhead move.

---

### WP5 — Keyboard: the Hindenburg keymap

Status: infrastructure done in v26.10.18.6 (data-driven keymap in `ui/keymap-default.js`, user overrides with collision reports, dispatcher with physical keys and AltGr, cheat sheet, docked palette, in-window menu bar with enabled state and modifier alternates). Editing keys wired in v26.10.18.8 (split, soft delete, cut, mute, solo, group editing, trim, nudge, select all, clip gain); still planned: copy and paste, fade at cursor, lift-cut, close gap on all tracks, Compare, move to track. Needs WP4. This is the most important UI WP (R10).

New files `ui/keymap.js` (the table), `ui/commands.js` (one function per
command, each taking the store and returning nothing). `Mod` is Cmd on Mac and
Ctrl elsewhere (`navigator.platform` / `userAgentData`). Keys are matched on
`event.key` plus modifiers. When focus is in a text input, only Esc and
Mod-combinations act.

Every command is also in a command palette (Mod+K): a filterable list of
command names with their keys, so everything is discoverable without a mouse.

Source of the bindings: Hindenburg PRO's own list,
<https://hindenburg.com/academy/shortcuts/shortcuts-hindenburg-2-pro/>.

**Single keys first (owner, 2026-10-16, as in Hindenburg):** every editing
action has a key with no modifier; ⌘ (Mod) is kept for file and app actions
(undo/redo, copy/paste, select all, import, export, save, palette,
settings) and as an alias for the editing keys below. Single keys are off
while a text field has focus (only Esc and Mod combinations act) and in
record mode (only the log keys). Changes to the table below, which the
collision test must accept:

- split **B** (alias Mod+B); cut and close gap **X** (Mod+X); cut this
  track only **Shift+X**; close gap on all tracks **Alt+X**
- mute clips **N** (Alt+Mod+M); fade **G** (Mod+F); clip gain **+ / -** on a
  selection (Shift+Mod+↑/↓), with time zoom on = / - only when nothing is
  selected; group editing **E** (Mod+G)
- mark in sync **Y** (Alt+Mod+S); resync **R** (Alt+Mod+R)
- zoom close/wide **Z**, fit **Shift+Z**, view back/forward **Alt+Z** / **Shift+Alt+Z**
- **Mod+S** saves a named version (a checkpoint named by time, plus an
  immediate backup; the message offers Rename); **Shift+Mod+S** asks for the
  name first. Autosave needs no key: every edit is on disk before it shows.

| Keys | Command | Does (API call) |
|---|---|---|
| Space | play/stop | transport play from playhead / stop |
| Shift+Space | play selection | play from in to out (or selected clips' span) |
| Home / End | to start / end | playhead 0 / project length |
| ← / → | back / forward | playhead ∓1 s (Shift: ∓5 s, Alt: ∓10 ms) |
| ↑ / ↓ | focus track | move focus to the track above / below |
| Tab / Shift+Tab | next / previous edit | playhead to next/previous clip edge on any track |
| J / K / L | shuttle and scrub | classic JKL, see WP26: L forward (press again: faster), J backward, K stop; hold K with L/J for slow scrub |
| . | speed toggle | normal ↔ fast playback, pitch preserved (WP26) |
| I / O | in / out | set in/out point at playhead |
| Mod+B | split | split selected clips at playhead; none selected: the focused track's clip under the playhead; with in/out set: split at both |
| Mod+X | cut and close gap | ripple-delete in→out on all tracks; else the selected clips' span on all tracks |
| Shift+Mod+X | cut on this track only | ripple-delete in→out on the focused track only |
| Backspace / Delete | delete, leave gap | delete selected clips (`delete_clips`); in transcript focus: cut words |
| Q / W | trim start / end to playhead | `trim_clip` on selected (or focused-track) clip |
| Mod+Z / Shift+Mod+Z | undo / redo | |
| Mod+A | select all on track | all clips of the focused track |
| Alt+Mod+A | select all | all clips on all tracks |
| Shift+End / Shift+Home | select to end / start, this track | `clips_from` / `clips_until` (focused track) |
| Shift+Alt+End / Shift+Alt+Home | select to end / start, all tracks | `clips_from` / `clips_until` (all) |
| Esc | clear selection and in/out | |
| Mod+← / Mod+→ | nudge | `shift_clips` selection ∓10 ms (Shift: ∓100 ms) |
| Mod+↑ / Mod+↓ | move to track | selected clips to the track above / below (`move_clip` per clip, one commit via a new op `move_clips_to_track`) |
| Shift+Mod+↑ / Shift+Mod+↓ | clip gain | selection ±1 dB, coalesced |
| Shift+Alt+← / Shift+Alt+→ | clip pan | selection pan ∓0.1, coalesced (not in Hindenburg) |
| Alt+Mod+M | mute clips | toggle `muted` on the selection |
| Shift+M / Shift+S | mute / solo track | focused track; solo is exclusive and overrides mute (WP24.1); Shift+Alt+S adds to the solo set |
| Mod+F | fade | selected clips: 500 ms fade in and out (if both already set, clear them) |
| Mod+= / Mod+- | zoom | ×2 / ÷2 around the playhead |
| Mod+H | zoom to selection | |
| Mod+T | import | open file picker (upload) |
| Mod+E | export | open the export dialog (WP11) |
| Shift+Mod+T | transcribe | transcribe the focused track's media (WP9) |
| Mod+L | automix | `command automix` |
| Alt+Mod+P | Auto-Silence | `command auto_silence` on the selected tracks or all speech tracks |
| Alt+Mod+S | mark in sync | `mark_in_sync(selection, main=the selected clip on the topmost track)` |
| Alt+Mod+R | resync | `resync(selection)` |
| Alt+Mod+1 / Alt+Mod+2 | sync point | set the first / second sync point on the clip under the playhead (focused track); the second clip with a point gets aligned (see "Sync workflow") |
| Shift+Alt+Mod+R | resync to end, all tracks | select `clips_from(playhead)` then resync |
| Mod+K | command palette | |
| ? | help | the keymap as a table |

New op needed: `ops.move_clips_to_track(p, clip_ids, direction: int)`. It moves
each clip to the track `direction` steps away, keeping start. Tests first, in
`tests/test_ops.py`.

Tests: `ui/tests/keymap.test.js`: every binding resolves to an existing
command; no two bindings collide; Mod resolves to Meta on Mac and Control
elsewhere; text-input focus blocks plain keys.

Acceptance: the user can import, split, cut, trim, nudge, mute, resync and
undo without touching the mouse.

---

### WP6 — Mouse editing

Status: open. Needs WP4.

All on the canvas, hit-testing in `timeline.js` (pure function, tested):

- Click clip: select (Shift+click adds, Mod+click toggles). Click empty
  space: clear selection, set playhead.
- Drag clip body: move (horizontal) and between tracks (vertical); the whole
  selection moves together. Commit **once on mouse-up** (`shift_clips` and
  `move_clips_to_track`); draw a ghost while dragging.
- Drag clip edge (6 px zone): trim (`trim_clip`) on mouse-up.
- Drag the clip gain line vertically: `set_clip gain_db` with coalesce key
  `clip-gain-<id>`, live while dragging.
- Alt+click on the gain line: add envelope point at that source frame
  (`set_clip_envelope` with the new list); drag a point to move it; Alt+click
  a point to delete it.
- Drag top corners of a clip: fade in/out.
- Snap to clip edges and playhead within 8 px (hold Mod to disable).

Tests: hit-testing and drag-to-edit translation as pure functions in
`ui/tests/edit.test.js` (given state + pointer events → expected API calls).

---

### WP7 — Transcript panel

Status: open. Needs WP4, WP1.

`ui/transcript.js`. Renders `GET /api/words` as paragraphs: a new paragraph
whenever the track (speaker) changes or a pause is longer than 1.5 s. Each
paragraph starts with the track name, coloured like the track.

- Click a word: playhead to its start. While playing, the current word is
  highlighted and kept in view.
- Words under muted clips are shown struck through and greyed.
- Select words with the mouse or Shift+←/→ (word by word); Backspace/Delete
  sends `command cut_words {indices}`. This is the "edit audio with text"
  feature (R6). The cut always applies to all tracks.
- Enter on a selected single word: edit its text inline; Enter saves
  (`PUT /api/word`), Esc cancels.
- After any state change, refetch words (they are derived; never patch them
  locally).

Tests: paragraph grouping and word-selection-to-indices as pure functions.

---

### WP8 — History panel

Status: first half done in v26.10.18.4 (undo context and session markers) and the History panel in v26.10.18.15 (paged steps, markers, restore, undo-across-marker toast); hover preview, pinned steps and checkpoints (WP31) open. Needs WP4.

`ui/history.js`. Shows `GET /api/history` as a tree: the current branch as a
list, with abandoned branches as indented, dimmed entries under the node
they split from. Each entry shows its label and a relative time in Helsinki
local time (the browser's local time is fine on the user's machines). The
head is highlighted. Nothing is ever deleted.

Undo semantics follow "Who undoes the undoers"
(<https://unsung.aresluna.org/who-undoes-the-undoers/>): undo is a quick,
tactical tool; history is a strategic, append-only record. Keep the two
apart:

- **Mod+Z / Shift+Mod+Z move along the current branch only.** An edit after
  undo starts a new branch and the old one is kept (already true in
  `History`), but it is reachable **only** from this panel, never by Mod+Z.
- **Restoring from the panel is ledger-style.** Clicking an entry and pressing
  "Restore" (or Enter) does **not** rewind: it appends a new step
  "restored to ‹label›" whose state equals that entry's. The current state is
  therefore never stranded, and Mod+Z after a restore undoes the restore.
  New `History.restore(node)` (= `commit(f"restored to {label}", state_of(node))`).
  Keep `goto` for internal use and tests only; the API exposes `POST /api/restore`.
- **Hover preview:** hovering an entry draws that state's clips as ghost
  outlines over the timeline, read-only, so you can see what you would get
  before restoring.

**Session markers** (owner, 2026-10-16): opening and closing a project
writes a marker into the current edit's history ("opened 16.10. 16.40
Helsinki"). When Mod+Z crosses one, the message says so without blocking:
"Undid a step from yesterday: cut at 12:31 · Redo". Markers are visible in
the panel as dividers between sittings.

**Stateful undo.** Each node also stores the UI context at the time of the
edit: `{selection, focus_track, playhead, view: [first, last], in, out}`.
`History.commit(..., context=dict)` saves it in a new `nodes.context` column.
`undo()`, `redo()` and `restore()` return the context of the step being
undone or redone. The UI then restores that selection and focus, scrolls the
timeline so the changed range is visible, and flashes the clips that changed
(diff of clip ids and positions between the two states, computed client-side).
The playhead stays where it is unless the changed range is off-screen.
Undoing never leaves the user wondering what just happened.

Tests: tree layout from a node list as a pure function;
`test_restore_appends_a_step_and_keeps_the_current_state_reachable`,
`test_undo_after_restore_undoes_the_restore`,
`test_mod_z_never_enters_an_abandoned_branch`,
`test_undo_returns_the_context_of_the_undone_step`,
`ui/tests/undo-flash.test.js` (changed-clip diff).

---

### WP9 — Background jobs and transcription

Status: done in v26.10.16.14 (local faster-whisper jobs, cancel, yield to playback/input; Colab transcription left open and reports "not available yet"; no real-model run recorded). Needs WP1.

New file `src/kuulas/jobs.py`: a small job runner on a
`ThreadPoolExecutor(max_workers=media.workers())`.

```python
class Jobs:
    def submit(self, kind: str, title: str, fn: Callable[[Callable[[float], None]], Any],
               on_done: Callable[[Any], None]) -> str   # job id
    def list(self) -> list[dict]   # {id, kind, title, progress 0..1, state, error}
    def cancel(self, job_id: str) -> None   # cooperative: fn checks a flag
```

`GET /api/jobs` lists them; the UI shows a small jobs indicator in the toolbar.

**Jobs never make the UI sluggish (ground rule 14):**
- An **interactive signal** (playing, scrubbing, dragging, or input in the
  last 2 s) drops jobs to one low-priority worker; idle gives them all cores.
- Jobs work in chunks and yield between them, so an interactive request
  never waits behind a long job.
- Jobs compute on a snapshot of the state, never holding the session lock,
  and commit at the end only if the inputs they used are unchanged;
  otherwise they recompute (or, where WP32 applies, become suggestions).
- CPU-heavy Python and every plug-in render run in a process pool
  (true parallelism, and a crashing plug-in fails only its job).
- Disk I/O from jobs is throttled while playing; playback prefetch goes first.
- Every job shows progress with time remaining and can be cancelled.

Transcription command `transcribe` `{media_ids: [...], model?: "small",
language?: "fi"|None, backend: "local"|"colab"}`:

- **local**: one job per media, run in parallel. Each job calls
  `transcribe.local(path, rate, model, language, cpu_threads=max(1,
  cores // jobs))` (add the `cpu_threads` parameter; faster-whisper accepts
  it). The source path is the linked file or the working FLAC.
  `on_done` calls `session.set_transcript(media_id, words, "transcribe <name>")`.
- **colab**: needs a decision from the user, so do not build it in this WP.
  `colab-transcribe` (podcast repo) only accepts Hindenburg sessions. The
  recommended route is to add a plain-audio mode there
  (`--audio <file> --json <out>`) that writes word JSON. kuulas would then run
  `uvx --from "git+https://github.com/ollisulopuisto/podcast#subdirectory=colab-transcribe" colab-transcribe --audio … --json …`
  and import the result with `transcribe.parse`. Write this as an open
  question in `ROADMAP.md`.

Speaker labels: words get `spk = ""`; the UI names speakers by track.

Tests: `test_jobs.py` (progress, error capture, cancel, parallelism with a
fake fn and a barrier), `test_transcribe_job.py` with `transcribe.local`
monkeypatched to return fixed words.

---

### WP10 — speechmix voice chain per track (automixer, R4)

Status: open. Needs WP1, WP9.

Command `process_voice` `{track_ids: [...], plugin?: path, plugin_state?: str}`
runs `speechmix.chain.process` on every **media** used by speech clips of those
tracks, as parallel jobs, and stores each result as new media (a *variant*).

- Settings object (duck-typed, read by `chain.process`):
  `SimpleNamespace(high_pass_hz=chain.HIGH_PASS_HZ,
  peak_threshold_db=chain.PEAK_THRESHOLD_DB,
  leveler_threshold_db=chain.LEVELER_THRESHOLD_DB, declick=True,
  declick_sensitivity=0.5, rider=True)`. These constants live in
  `speechmix.chain`; do not copy their values.
- `speaking=` mask: from `analysis.speech_lanes` for that track (the rider
  needs it; see automixer `processor.py` comments).
- Call with `gain_db=0.0, speech=True, target_lufs=None`.
- Output length equals input length (`chain.process` guarantees it), so a
  variant can replace its source in a clip without moving anything.
- Model: add `Media.variant_of: str | None` and `Media.variant: str` (e.g.
  `"voice chain"`). New op `use_variant(p, clip_ids, media_id)` swaps
  `Clip.media` between a source and its variant, one commit. The inspector
  shows a "Processed" toggle.
- Variants are written by `MediaStore` as 24-bit FLAC working files
  (`store.add_array(audio, name, variant_of)`, a new method; test it).

Tests: with a synthetic voice file, `process_voice` creates one variant per
media and swaps clips; undo restores the original media; the variant has
the same frame count.

---

### WP11 — Export

Status: done in v26.10.16.14 (WAV/FLAC/MP3, selection, stems, mastering, versioned names; 49 export tests, mastering tests need a writable `NUMBA_CACHE_DIR`; export dialog is UI work, not built). Needs WP1.

Command `export` `{path, format: "wav"|"flac"|"mp3", bit_depth: 16|24,
mp3_kbps: 64..320 (default 128 mono master, 192 stereo), range?: [start, end],
master_lufs?: float}`.

- **MP3:** render as for WAV (float), then encode with ffmpeg's `libmp3lame`
  (CBR at `mp3_kbps`, channels follow the master: mono or stereo, WP27), from
  a temporary float WAV, never re-rendered. ID3 title from the edit name.
  Test: the MP3 decodes, its length is within one MP3 frame of the WAV, and
  its integrated loudness is within 0.5 LU of the WAV's.

- Render with `mixer.mix` in 30 s blocks, **in parallel** (thread pool;
  numpy releases the GIL in the heavy parts), written in order to a
  `.partial` file, renamed when complete. Progress through a job (WP9).
- `master_lufs` set: render to a float32 memmap first, then run
  `speechmix.programme.master(audio, rate, target)` and write the result.
  Report `MasterResult` (gain, measured LUFS, limiter cost, reached) in the job
  result. Over 3 hours, refuse with a clear error (memory).
- The exported file gets a BWF `bext` with TimeReference 0 and the project name.
- **Versioned names, no overwrites:** the name template is remembered per
  project (default `{edit} v{n}.{ext}`, e.g. `Jakso 42 v3.mp3`). `n` counts
  up per edit only when the result would differ: if the edit state and
  settings hash equal the last export's, nothing is rendered and the message
  says "Unchanged since v3 · Show file". Optional setting: also keep
  `{edit} latest.{ext}` current for a fixed upload path.
- **Each export is a checkpoint** ("v3 exported, MP3 128 kbps"), so versions
  can be compared (WP31) and restored.
- **Provenance in the file:** version, edit, project and step id go into ID3
  tags (MP3) or the BWF description (WAV).
- **Quick export (ground rule 16):** Mod+E exports at once with the last
  settings and shows "Exported MP3 · 128 kbps · mono → … · Undo · Change…";
  Alt+Mod+E opens the dialog. Presets ("Podcast MP3", "Archive WAV") are
  commands of their own.

**Three exports, one engine (owner, 2026-10-16).** Each has the quick
behaviour above, its own remembered settings, and works on the whole edit
or on a selection:

| Export | Key | What |
|---|---|---|
| **Mix** | Mod+E | the programme as heard, the whole edit |
| **Selection** | Shift+Mod+E | in→out, or the span of the selected clips: "send this bit for an opinion". Named `{edit} {from}–{to} v{n}`, with a 30 ms fade at each end so it doesn't click. MP3 by default |
| **Tracks** | Alt+Shift+Mod+E | **one file per track**, whole edit or selection, for mixing elsewhere (Logic, Pro Tools, Reaper) |

**Track export, for "edit in kuulas, mix in Logic":**
- Every file starts at the same moment and has the same length (silence where
  a track has no audio), so they line up when dropped into any DAW at 0.
  Each carries a BWF time reference of the programme start too, for DAWs
  that place files by timestamp.
- Mono tracks stay mono; stereo stays stereo. 24-bit WAV at the project rate
  by default.
- The edit is applied: cuts, crossfades, clip gain, fades, muted pieces as
  silence.
- **Processing, chosen per export (remembered):**
  - **dry** (the default for "mix elsewhere"): no track or bus effects,
    no track automation, no ducking, no master;
  - **as heard**: each track through its own layers, gain and automation,
    without buses or master;
  - rendered restoration (dxRevive, voice chain) is included or not by its
    own switch, because it belongs to the source rather than to the mix.
- Optional: buses as their own files; a text file listing the tracks,
  roles, start time and settings, so the mix session can be rebuilt.
- Named `{edit} – {track}.wav` in a folder `{edit} tracks v{n}/`.
- Role stems (WP19c) are the same engine, grouping tracks by role.
- Later, by owner decision: AAF/OpenTimelineIO export with the clips still
  separate (the `pyaaf2` and OpenTimelineIO libraries exist), so the
  edit can be continued in another editor rather than just mixed.

Tests: a selection export equals that range of the mix with the edge fades;
track files are sample-aligned, equal length, and sum (dry, mono to centre)
to the dry mix; dry excludes ducking and effects; as-heard matches each
track's contribution to the mix.

Tests: export of a known project equals `mixer.mix` over the whole length
(bit-exact for float WAV); parallel and serial renders are identical;
`master_lufs=-16` measures -16 ± 0.5 LU with pyloudnorm; a crash
(exception mid-render) leaves no file at `path`.

---

### WP12 — Basic multitrack recording (R22, Mac first)

Status: open. Needs WP1, WP2.

Standard APIs only: `sounddevice.InputStream` (CoreAudio on Mac, WASAPI on
Windows). No exclusive modes, no ASIO, no loopback, no aggregate-device
creation. If a user wants several interfaces, they make an Aggregate Device in
macOS Audio MIDI Setup themselves; kuulas sees it as one device.

New file `src/kuulas/recorder.py`.

```python
def devices() -> list[dict]      # inputs only: {index, name, channels, default_rate}
class Recorder:
    def __init__(self, session: Session, device: int | None, channels: list[int],
                 names: list[str]): ...
    def start(self, at: int) -> None     # timeline frame where the take starts
    def stop(self) -> Project            # imports the take, one commit
    def levels(self) -> list[float]      # peak dBFS per armed channel since last call
```

- **Monitoring is the audio interface's job.** kuulas does not route input to
  output in software in v1 (Python latency would be audible). The record
  view says so: "Monitor through your interface's direct monitoring." Software
  monitoring with effects waits for a native engine (see WP2).
- Sample rate: the project rate (48000). If the device cannot open at that
  rate, refuse with a message naming the device's rate; do not resample live.
- The audio callback only copies the block into a `queue.Queue`. A writer
  thread writes each armed channel to its own file
  `recordings/<take>-<name>.wav.partial` as **raw 24-bit little-endian PCM**,
  plus a sidecar `<take>.json` (`rate, channels, names, start, created`)
  written before the first block.
- `stop()`: the writer finishes; each raw file is wrapped as a WAV (soundfile
  writes the header around the same samples), the `.partial` is removed, and
  the WAVs are imported with `copy=False` (linked: they already live in the
  project) and placed as clips at `start` on new tracks (or the armed tracks),
  all marked in one sync group (`mark_in_sync`, main = first channel).
- Crash recovery: `Session.__init__` looks for `*.wav.partial` + sidecar and
  finishes them the same way, as one commit labelled `recover recording`.
- Overruns (`status.input_overflow`) are counted and shown; never silently dropped.
- UI: a record panel (device, channel checkboxes with names, level meters, Record/Stop).
  Keys: Shift+R arm the focused track, Mod+Space record. Both bindings match Hindenburg.

**Foolproof recording mode (modal).** It must be near impossible to stop a
recording by accident:

- Recording is a **mode**. Mod+Space enters a full-window recording view;
  the timeline, panels and every edit key are disabled. Shown: big elapsed
  time, a level meter and clip light per channel, the channel names,
  remaining disk time, and a "Recording" banner.
- **Nothing stops it except the deliberate stop gesture**: press and hold
  the Stop button, or hold Shift+Mod+Enter, for 2 seconds, with a visible
  fill bar. Releasing early cancels. Space, Esc, Enter and every other key
  do nothing (Space is the classic accidental stop).
- **Logging while recording** is the one thing you can edit. The recording
  view has a log panel, a list of markers on the take, and keys that only
  touch that list:

  | Keys | Does |
  |---|---|
  | M | drop a marker *now minus the reaction offset* (default 3 s, settable; you press after you hear the good bit). The name field opens; type and press Enter, or keep listening (Enter not needed) |
  | D | start / end a cut candidate (WP18) on the take |
  | ↑ / ↓ | select a marker in the log |
  | Enter | rename the selected marker inline (Esc cancels) |
  | ← / → | move the selected marker ∓1 s (Shift: ∓5 s), never past "now" |
  | Backspace | delete the selected marker (Mod+Z undoes, inside the log only) |

  **Not in this WP (v2, parked in ROADMAP.md):** scrubbing and playing the
  take back *while it keeps recording*, to place a late-logged marker by ear.
  It is feasible (the raw `.partial` files can be read as they grow, through
  a second output stream), but it needs its own design for monitoring so the
  user never confuses playback with the live input.

  While a name field has focus it receives the keys, and the stop gesture
  still works (it needs a hold). Markers are anchored to the take's
  recording clock, so after stop they land on the take's clips as `note` /
  `cut` markers (WP18) and follow every later edit. The log is written to
  the take sidecar (`<take>.json`) **on every change**, fsynced, so a crash
  keeps the log as well as the audio. Endpoint: `PUT /api/record/log`
  (whole list, versioned to reject stale writes).
- **The backend owns the recording, not the page.** Closing or reloading the
  tab, a UI crash or a lost connection never stops it. Reopening the page
  shows the recording view again. `POST /api/record/stop` requires
  `{"held_ms": >= 2000}` so that a stray call from other UI code cannot stop
  it. The page sets `beforeunload` to warn.
- **The machine must not sleep**: on Mac run `caffeinate -i -w <pid>` (a
  standard system tool) for the duration; on Windows call
  `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` via `ctypes`.
- **Trouble never ends the take silently.** On low disk (under 30 min left)
  or after an input overflow, show a loud warning but keep recording. If the
  device disappears, close the current files cleanly, show a full-screen
  error, try to reopen the same device every second, and continue as a new
  take in the same sync group when it returns.
- Quitting the app (Ctrl+C, window close) while recording finishes the take
  first (signal handler), then exits.

Tests (no hardware; fake `InputStream` feeding known blocks):
`test_stop_without_a_held_gesture_is_refused`,
`test_closing_the_session_ui_does_not_stop_the_recorder`,
`test_marker_dropped_during_recording_lands_on_the_take`,
`test_marker_reaction_offset_places_it_earlier`,
`test_renamed_and_moved_markers_survive_a_crash_mid_take`,
`test_marker_cannot_move_past_now`,
`test_log_markers_follow_edits_after_stop`,
`test_device_loss_closes_files_and_resumes_as_a_new_take_in_the_same_group`,
`ui/tests/record-mode.test.js` (every key except M and the hold gesture is
ignored; releasing the hold early cancels),
`test_take_writes_one_file_per_channel_with_the_right_samples`,
`test_stop_places_clips_at_the_start_frame_in_sync`,
`test_partial_take_is_recovered_on_reopen`,
`test_overflow_is_counted`, `test_wrong_rate_is_refused_with_the_device_rate`.
Hardware test `tests/hardware/test_record.py` for Mac, then Windows.

---

### WP13 — Hindenburg session import

Status: done in v26.10.16.14 as import only (`import_nhsx`; original XML kept under `extra["nhsx"]`; Hindenburg export not built, so the round trip is open). Needs WP1.

Command `import_nhsx` `{path}` using `nhsx.read` (`../podcast/packages/nhsx/src/nhsx/read.py`)
and `nhsx.pipeline.tracks`. Map Hindenburg regions to clips (start, offset,
length in frames), region gain to `gain_db`, region fades to fades, and
track names. Words stored in the session become transcripts. Read
`packages/nhsx/README.md` and the app `CLAUDE.md` files about the `.nhsx`
word clock before starting. Test against the fixtures under `podcast/packages/nhsx/tests`.

---

### WP14 — Parallel analysis

Status: done in v26.10.16.3 (speech lanes, one track per core; auto_silence and
automix as jobs wait for WP9). Needs WP0.

`analysis.speech_lanes`: compute `track_levels` for all speech tracks in a
thread pool (`media.workers()`). Tests: the result equals the serial result
exactly. Also run `auto_silence` and `automix` as jobs (WP9) once WP9 lands.

---

### WP15 — Desktop wrapper

Status: first cut done in v26.10.18.4 (`desktop.py`, `kuulas`/`kuulas open --window`, recents, native dialogs, CI workflow); not yet seen by a person. **Moved up by the owner (2026-10-18): the wrapper is part of the first version (M1)**, right after WP5, so the keymap can assume a native window (Cmd+T, Cmd+W, F6, Cmd+L free). Packaging and signing stay a later decision.
**Owner decisions 2026-10-18:** first-version (M1) scope is the wrapper plus the
clipboard (WP46); Compare (WP45) comes later. Technology: `pywebview` (the owner
has used it in other apps and dislikes Electron). Platforms: the owner can test on
Mac and Windows; CI builds all three (Mac, Windows, Linux) on GitHub Actions
(tests plus the wrapper build); if time is critical, start with Mac only. A
workflow file is committed locally; the owner pushes it (agents never push).
Known pywebview limits to design around: Linux needs system web-view packages
(GTK WebKit2 or Qt); Windows needs the WebView2 runtime; macOS WKWebView is
Safari's engine (Safari quirks: pinch comes as gesture events); native menus are
basic; no built-in updater; file drops give paths only through pywebview's own
API (use it to link media in place); signing and notarising the Mac app is a
separate chore.

Wrap the app with `pywebview` (standard OS web views: WKWebView on Mac,
WebView2 on Windows). `kuulas` without arguments opens a window with a
recent-projects list. Packaging (PyInstaller, signing) is a separate,
later decision; record it in `ROADMAP.md`.

---

### Sync workflow (read before WP5, WP12, WP16)

This is the user's model, and the UI must make it the obvious path:

1. **In sync by default.** Files that arrive together (one import, one
   recording take) are one sync group from the start (WP1, WP12).
2. **Align by eye, then sync.** For a file that is not in the group, the user
   slides it into place on the timeline (mouse drag, or Mod+←/→ nudges at
   10 ms / 100 ms, Alt+←/→ playhead steps of 10 ms for checking), selects it
   with one or more clips that are already right, and presses Alt+Mod+S
   ("mark in sync"). Done. It is now in the group, and every subclip it is
   later split into stays in it.
   **Sync points** make step 2 exact without sliding by eye. Typical case:
   one Zoom recording plus one local recording of the same talk; both
   contain the same sounds (the host's voice, a clap, a laugh). Put the
   playhead on a sharp sound in clip A and press Alt+Mod+1 ("sync point");
   put it on the same sound in clip B and press Alt+Mod+1 again. kuulas
   moves B so the two points coincide on the timeline and marks A and B in
   sync. A **second** pair of points near the end (Alt+Mod+2 in both) also
   measures clock drift: if the two offsets differ, B is replaced by a
   resampled variant (ratio from the two point distances; WP10 variant
   mechanism, ffmpeg `aresample`) so it stays in sync for the whole length.
   New op `ops.align_points(p, clip_a, point_a, clip_b, point_b)` (points in
   source frames) plus Session command `align_two_points` for the drift
   case. Tests first: one pair moves B exactly; two pairs with a 0.01 %
   rate difference produce a variant whose residual is under 1 ms at both
   points. Pending points are UI state and shown as flags on the clips.
3. **Edit freely, resync when needed.** Alt+Mod+R resyncs the selection;
   Shift+Alt+Mod+R resyncs everything from the playhead on, on all tracks
   (the fix for an accidental one-track cut).

The UI shows group membership on each clip (a small coloured tag in the clip
header, one colour per group) and shows clips that are out of sync with their
group, e.g. a red tag with the offset in ms. "Out of sync" is computed client-side by
comparing `start - offset - sync_origin` with the main clip's piece (the same
reference rule as `ops.resync`; port it as a pure function and test it
against the Python results on the same fixtures).

WP16 below is an *assistant* for step 2, for when eyes and hands are slow
(different lengths, drift, dropouts). It is not required for the workflow.

---

### WP16 — Align recordings by sound (remote, phone and Zoom recordings, R23)

Status: open. Needs WP1, WP9. Optional helper for step 2 of the sync
workflow; build it after WP5–WP8.

The problem: a remote interview arrives as files that share no clock. There
is a Zoom or phone recording of everyone, plus each person's local recording,
and the files have different lengths and start times. Today people line them
up by eye and ear. Timestamps (sync groups, BWF) cannot help because there are
none in common, so this WP aligns by *sound*.

Command `align` `{reference_clip, clip_ids}`: the reference is the recording
that hears everyone (the Zoom/phone mix). For each other clip:

1. **Offset.** Measure the lag with `speechmix.chain.lag_samples` (envelope
   cross-correlation in 1 ms bins; robust to codecs and level) between the
   reference and the clip, in windows of 60 s every 5 minutes along the
   overlap. Search the whole overlap for the first window. After that, search
   ±2 s around the previous lag.
2. **Drift.** Fit lag against time (least squares on the windows whose
   correlation peak is clear, i.e. peak / second peak ≥ 1.5). A slope above
   1 ms per 10 minutes is drift: the two clocks run at different rates.
   Correct it by making a resampled *variant* of the clip's media (WP10's
   variant mechanism; ffmpeg `aresample` with the exact ratio
   `1 + slope`), so the original is untouched and the fix can be undone.
3. **Jumps.** Zoom and phone recordings drop audio and skip. A window whose
   lag differs from the fit by more than 20 ms marks a jump. Split the clip at
   the quietest point between the last good window and the jumping one
   (lowest `analysis.track_levels` value in that stretch), and align each
   piece on its own.
4. Place the clips, then `mark_in_sync` all of them with the reference as
   main, so later edits can be resynced by timestamp (R16).
5. Report per clip: offset, drift in ms per hour, pieces made, and windows
   that could not be matched. Never move a clip on a weak match: leave it and
   say so.

Run as a job (WP9), with each clip in parallel.

Tests (synthetic, `tests/test_align.py`): a local track that is the reference
delayed by 2.345 s aligns within 1 ms; a track resampled by 1.0001 (6 ms
drift per minute) is detected and corrected so that residual lag is under 2 ms
at both ends; a track with 1.2 s of audio removed in the middle is split there
and both pieces align; files of very different lengths (reference 60 min,
local 20 min starting at minute 15) align; pure noise against the reference
is reported unmatched and not moved.

UI: select the clips, Alt+Mod+G ("align by sound"), and the main clip is the
one on the topmost track. The result report appears in the jobs panel.

---

### WP17 — Clip bin (Hindenburg's clipboard)

Status: open. Needs WP4. Only after WP5–WP8.

A side list of saved clips and imported files to drag onto the timeline. Two
binding rules, from real complaints about Hindenburg:

- **Space never plays the bin.** Space is the timeline's transport, whatever
  has focus. Previewing a bin item needs its own explicit control (a play
  button on the item, or Alt+Space when the bin has focus). Previews play
  **at the level they will have in the mix**: loudness-matched to the
  programme (`speechmix.programme` measurement), never at raw file level.
  Someone listening on headphones must not be startled by a jump in level.
- **Dropping never trims to in/out.** Dragging or pasting a clip onto the
  timeline places it whole at the drop point. The in/out points affect only
  commands that name a range (Mod+X, Shift+Space, export range). They are
  shown clearly, and Esc clears them.

Tests: a keymap test that Space maps to the transport in every focus context;
a drop-handling test where in/out is set and the dropped clip keeps its full
length.

---

### WP18 — Cut candidates: mark on the first listen, decide on the second

Status: backend done in v26.10.18.16 and the panel with keys and a jump preview in v26.10.18.17; an engine skip list for a gapless preview, the overview ticks, breath detection and tuning on real recordings open. Needs WP1, WP4, WP5. High value: this is the user's core
editing loop.

The workflow: listen once and mark possible deletions without stopping. On
the second listen, delete some of them. Every remaining marker must still
point at the right audio, however much has been cut or moved since.

**Anchoring rule:** a marker stores *where it is in the recording*, never
where it is on the timeline. Its timeline position is derived from the clips
every time, exactly like transcript words (`transcript.timeline_words`).

Model (`model.py`), in `Project.markers: tuple[Marker, ...]`:

```python
@dataclass(frozen=True)
class Marker:
    id: str
    kind: str            # "cut" (candidate deletion) | "note" | "timeline"
    anchor: str          # "group" | "media" | "timeline"
    ref: str | None      # sync group id, media id, or None for timeline
    start: int           # group or media anchor: flicks on that recording clock
    end: int             # timeline anchor: project frames (docs/FORMAT.md)
    state: str = "open"  # "open" | "rejected"  ("applied" is derived)
    text: str = ""
```

- Creating a candidate over a clip that is in a sync group anchors to the
  group's recording clock (`Clip.recorded`), so it covers every track of the
  group. Otherwise it anchors to the clip's media. `kind="timeline"` markers
  (an ad break at 15:00) anchor to the timeline and only move by explicit
  edits. `ripple_delete` shifts them like track automation.
- `markers.place(p, marker) -> list[(start, end)]`: timeline spans, found by
  mapping the anchored range through every clip that plays it (main pieces
  for a group, any clip of the media for media anchors). Empty list means
  "applied" (all its audio has been cut). A partly cut marker returns its
  remaining spans.

Ops: `add_marker`, `set_marker` (state, text), `delete_marker`,
`apply_cut_marker(p, marker_id)`, which ripple-deletes each placed span on all
tracks (last span first so earlier spans stay valid) with the usual crossfades.

Keys (add to WP5):

| Keys | Does |
|---|---|
| D | while playing: first press starts a candidate at the playhead, second press ends it. Playback never stops |
| Alt+D | candidate from in to out, or over the selected words in the transcript |
| ] / [ | next / previous open candidate; playhead to 2 s before it (brackets: Hindenburg's cut-point keys; Alt+Tab is taken by Windows) |
| Shift+Space on a candidate | **preview the cut**: play 2 s before, skip the candidate, play 2 s after |
| Enter | apply the candidate (`apply_cut_marker`) |
| Backspace | reject it (kept, dimmed, state `rejected`) |
| Mod+Shift+D | show only open / all candidates |

UI: candidates are drawn as translucent bands across the lanes of their
group, with a list panel (time, duration, transcript text under it, state).
The transcript highlights candidate words. The engine needs a `skip=(a, b)`
option on `play` for the preview (test it in WP2's style).

Tests first (`tests/test_markers.py`):
- `test_marker_follows_its_audio_after_an_earlier_cut`
- `test_marker_follows_a_moved_clip`
- `test_partly_cut_marker_shrinks`
- `test_fully_cut_marker_reads_as_applied_and_undo_restores_it`
- `test_group_marker_covers_every_track_of_the_group`
- `test_applying_one_candidate_leaves_the_others_on_their_audio`
- `test_applying_a_split_candidate_cuts_every_span`
- `test_timeline_marker_shifts_with_ripple_but_not_with_clip_moves`
- `test_markers_round_trip_through_json_and_history`

---

### WP19 — Borrowed from other editors

Status: open. 19h markers, regions, chapter export and regions as files done in v26.10.18.20 (the formatter and file-name helpers earlier). 19a partners and edit targets (`edit_scope.py`, pure logic, not yet wired into the edit commands) done in v26.10.17.6. 19i onset detection (backend) done in v26.10.17.4; 19h chapter-list formatter (`chapters.py`) done in v26.10.17.5; 19f typed-time parser (`spot.py`, not yet bound to a key) done in v26.10.17.9. Each part is its own small WP (19a–19i), commit each separately.
Needs WP1, WP4, WP5. Every key below goes into `ui/keymap.js`, and the
keymap collision test (WP5) must still pass.

Not borrowed, by decision: spectral display and spot healing (Audition),
Remix (Audition), session view, warping and MIDI (Live), grid mode (Pro Tools).

#### 19a — Edit groups (Pro Tools edit groups, Reaper ripple scope)

Prevents the accidental one-track cut instead of only repairing it.

**The rule (decided with the owner, 2026-10-16; storyboard on the roadmap
page and in `docs/ui-sketches.html`): an edit that shifts time keeps the sync
group together; any other edit touches exactly what you selected.**

- Every edit has a **target** and a **kind**:
  - The target is either a **range** (in→out, selected words, a cut
    candidate) on some tracks, or a set of **clips**.
  - Time-shifting kinds: cut and close gap, ripple delete, insert, move or
    nudge, ripple trim. Everything else (gain, pan, mute, fades, FX, delete
    leaving a gap, trim without ripple) does not shift time.
- **Time-shifting edits expand their target** to the sync group:
  - a range expands to every track of the group;
  - a clip set expands to each clip's **partners**: the group's clips on
    other tracks that play the same stretch of recording (by
    `Clip.recorded`, WP30).
- **Other edits use the target exactly as selected.** A range applies to
  the selected tracks (default the focused one; Shift+↑/↓ adds tracks).
- Tracks outside any group: a time-shifting range edit applies to all
  tracks, as before.
- **Seeing the scope:** a range is highlighted on exactly the tracks the
  next time-shifting edit will touch. A selected clip's partners get a
  dashed outline, so the user sees what a move will take along before
  pressing the key.
- **Close gap on all tracks** (Alt+Mod+X): with in→out on a silent gap
  (left by Backspace or by a resync), ripple-delete that stretch on every
  track of the group. This is how one-track work is brought back into sync
  (storyboard scene 6).
- **Free from sync, on purpose** (owner, 2026-10-16): **U** toggles a clip
  (and the pieces later split from it) free from its group. A free clip is no
  one's partner, shows a grey unlinked icon and its offset ("+300 ms ·
  free"), and never gets a drift badge. U again re-links it: a drift badge
  appears if it is off, and resync puts it back.
- **Alt-drag** moves a clip alone. Afterwards a message asks "Keep this clip
  free from sync? · Free it · No"; nothing changes unless answered.
- **Three states, never guessed:** in sync (nothing shown), **free** (declared
  by the user, grey), **drift** (a time-shifting edit moved it relative to its
  group and nobody has said it is deliberate: red badge with the offset, and
  on hover the cause read from history, e.g. "since: cut on Anna at 12:31,
  group editing off"; actions Resync (R) and Free it (U)). A drift list in the
  markers panel steps through undecided drifts (] / [), with "Resync all"
  and "Free all".
- **Never overeager:** nothing ever resyncs automatically; "resync from the
  playhead" skips free clips and says so ("Resynced 14 clips · skipped 2
  free").
- Mod+G (or E, WP5) toggles group editing for the session. When it is off, the toolbar
  shows a persistent warning chip "Group editing off", because that state
  is how the accident happens.
- Shift+Mod+X stays the explicit one-track cut.
- `Session.edit_target(kind, target) -> target` applies the rule, so every
  command gets the same answer. `ripple_delete`, Q/W, nudges, moves and
  `cut_words` use it.

Tests (one per storyboard scene, plus edges): a range cut expands to the
group and not to an ungrouped music track; with grouping off only the
focused track is cut and shows drift; gain on two chosen clips touches
exactly those; nudging one clip moves its partners; Backspace leaves a gap
and shifts nothing; resync then close gap on all tracks equals the
group-wide cut; partners are found by recording time, not by timeline
overlap; the toggle is UI state, not history.

#### 19b — Connected clips (Final Cut Pro)

A music bed or sound effect attached to a moment in the speech moves with it
through ripple cuts.

- `Clip.attach: tuple[str, str, int] | None` = (`"group"`|`"media"`, ref,
  recording frame), the same anchoring as markers (WP18). The attached clip's
  start is the anchor's derived timeline position.
- After every edit, `Session` re-derives attached clips' starts
  (`ops.reflow_attached`, pure, part of the same commit). If the anchor's
  audio has been cut away, the clip keeps its last position and shows a
  broken-link badge.
- Alt+Mod+C attaches the selected clips to the speech under their start
  (the topmost speech track). Shift+Alt+Mod+C detaches them.
- Drawn as a thin line from the clip's start down to its anchor lane.

Tests: a ripple cut before the anchor moves the attached clip by the same
amount; a cut after it leaves the clip alone; a cut through the anchor breaks
the link and leaves the clip in place; undo restores everything.

#### 19c — Roles, stems and Match Loudness (FCP roles, Audition)

- `Track.role: str`, defaulting to `"dialogue"` for speech and `"music"` for
  music, plus `"effects"` or any custom name. The toolbar has role chips that
  mute or solo every track of a role.
- Export option `stems: true` writes one file per role (that role's tracks
  only, through their buses, without master gain or mastering) next to the
  mix, rendered in parallel.
- Command `match_loudness {clip_ids | track_ids, target_lufs}`: measure each
  clip's integrated loudness with speechmix's meter (mono as mono,
  consistent with the pan law) and set `gain_db` so each reaches the target.
  One commit. Clips under -70 LUFS (silence) are skipped and reported.

Tests: stems sum to the mix (within float error) when no master gain is
set; match_loudness brings three clips at -30/-20/-12 LUFS to -20 ± 0.3.

#### 19d — Actions, remappable keys, macros (Reaper)

- Every command in `ui/commands.js` has a stable id (`"edit.split"`,
  `"transport.play"`, ...). The keymap maps keys to ids.
- User bindings in `~/.config/kuulas/keys.json` (served by
  `GET/PUT /api/settings/keys`) override defaults. A Keys panel lists every
  command with its binding, lets you press a new combination, and shows
  conflicts before saving.
- Macros: a named list of command ids (with fixed args) saved in the same
  file, runnable from the palette and bindable to a key. All edits a macro
  makes are **one undo step**, done with a shared `coalesce` key, which
  needs `History.commit` to accept a macro run id.

Tests: user binding overrides the default; conflict detection; a three-step
macro undoes in one step.

#### 19e — Alternative takes (Pro Tools playlists, FCP auditions)

- Alt+Mod+T on two or more selected clips stacks them into one **take set**
  at the first clip's position: `Clip.takes: tuple[Take, ...]`, `Clip.take:
  int` (active). `Take = (media, offset, length, gain_db)`.
- Alt+] / Alt+[ switches to the next / previous take. If the new take is
  longer or shorter, everything after it on the clip's edit group ripples by
  the difference, so later material stays in sync. One commit per switch.
- The clip shows "2/3" in its header.

Tests: switching takes changes the heard audio; a longer take ripples later
clips of the group; switching back restores positions exactly.

#### 19f — Spot (Pro Tools spot mode)

`=` opens a time field in the toolbar. Typing `h:mm:ss.mmm` (or `+/-` and an
offset in ms) and pressing Enter moves the selected clips' start there,
keeping their spacing (`shift_clips`), or moves the playhead when nothing is
selected.

Tests: parsing of `1:02:03.500`, `+120`, `-0.5s`; moving a selection keeps
spacing.

#### 19g — Skimming (Final Cut Pro)

`S` toggles skimming. When on, moving the pointer over the timeline plays
short grains of audio (80 ms) at the pointer position without moving the
playhead. The engine gets `scrub(at)`: render 80 ms with `mixer.mix` and play
it immediately, at most 30 grains a second, and the newest grain replaces any
queued one. Skimming is off while playing.

Tests: grain throttling and replacement (engine `_render` style, fake stream).

#### 19h — Markers, regions and batch export (Reaper region render matrix)

- WP18's `kind="timeline"` markers, plus `kind="region"` (a named range).
  M adds a marker at the playhead; Shift+M is taken (track mute), so a
  region is in→out plus Alt+M.
- Command `export_regions {format, ...}`: one file per region, named by
  its text, rendered in parallel (WP11 machinery).
- Export a chapter list as text (`hh:mm:ss Title` per line) and JSON. That
  is a file, not a publishing integration.

Tests: one file per region with the right length; chapter list times match
the markers after a ripple cut.

#### 19i — Tab to transient, and to word (Pro Tools Tab to Transient)

Tab moves the playhead to the next **edit point**; `'` (apostrophe) cycles
what an edit point is, shown in the toolbar:

1. clip edges on any track (default, as in WP5),
2. **transients** on the focused track,
3. **word starts** in the transcript (focused track's words).

Shift+Tab goes backwards in every mode. Transients are where cuts land
cleanly before a consonant or a breath.

Transient detection (`src/kuulas/onsets.py`), per media, computed once at
import (a job) and cached as `caches/onsets/<key>.npy`, int64 flicks from the media's start (docs/FORMAT.md; the earlier "source frames" wording is superseded):

- 1 ms envelope bins (abs max per bin, as `speechmix.chain.lag_samples`
  builds its envelope; reuse that construction, do not invent another).
- An onset is a bin whose level is at least 12 dB above the mean of the
  preceding 20 ms and above the media's noise floor plus
  `speechmix.grid.FLOOR_MARGIN_DB` (`grid.noise_floor` on the 20 ms
  envelope). Keep at most one onset per 50 ms (the strongest).
- Refine each onset to the sample: the first sample in its bin whose
  magnitude exceeds half the bin's peak.
- Mapped to the timeline through the clips, exactly like words.

Tests: clicks at known samples in noise are found within 1 ms; a steady tone
yields one onset at its start; onsets under a muted or trimmed-away part are
not offered; cached onsets are reused on reopen.

---

### WP20 — Copy clips between projects without bloat

Status: open. Needs WP1, WP4. Also the mechanism under the clip bin (WP17).

Hindenburg copies the **whole source file** into the target session when a
clip comes from another session's clipboard. A two-second soundbite from an
hour-long interview costs the full hour. kuulas copies the least that keeps
the clip playable.

Clipboard format (`application/x-kuulas-clips+json`, also written to the
system clipboard as text so it works across windows):

```json
{"rate": 48000, "source_project": "<folder>",
 "clips": [Clip.to_dict ...],
 "media": [{"sha256", "name", "channels", "frames", "linked_path"?,
            "working_file"?, "ranges": [[first, last], ...]}],
 "transcripts": {"<media id>": [words inside the ranges only]}}
```

Paste (`Session.paste(clipboard, at)`), per media, in this order:

1. **Already here.** The target store has that SHA-256: reuse it, copy nothing.
2. **Linkable.** `linked_path` exists and still hashes the same: link it in
   place (`import_file(copy=False)`), copying nothing.
3. **Otherwise copy an excerpt**: only the union of the clips' ranges plus
   `HANDLE_SEC = 2.0` on each side, read from the source project's working
   file, written as 24-bit FLAC (lossless if the source subtype allows). New
   fields on `Media`: `excerpt_of: str | None` (the original's SHA-256) and
   `excerpt_start_flicks` (where the excerpt begins in the original).
   Clip offsets are shifted by the excerpt start in frames. The excerpt
   inherits its original's sync origin plus `excerpt_start_flicks`
   (docs/FORMAT.md, "Sync per media"), so sync groups and markers still line
   up. Transcript words are sliced to the excerpt and shifted by the same
   flicks.
4. If the original later turns up in this project (same SHA-256), an op
   `expand_excerpt` can swap clips back to the full media with exact
   offsets.

**Pick what to import from another project** (owner, 2026-10-16; Hindenburg
imports a whole clipboard): "Import from project…" (Mod+Shift+I) opens
another project read-only in a picker, without opening it as the current
project. It lists that project's clip bin, its bits (WP42), its named
regions and markers, and its edits, from which an in→out range can be taken.
Each item shows name, length, the transcript text it contains, the speaker
(WP41) and its series usage (WP38). Items are picked with checkboxes,
filtered by transcript search or speaker, and previewed with their own play
button or Alt+Space (plain Space never plays a list, R24). Only the picked
items come in, through the paste rules above, so a picked 20 s bit never
brings its hour-long source. The picker remembers its last filters (ground rule 16).

Tests: picking 2 of 10 bin items imports exactly those 2; the imported
media is excerpts with handles (or reused by hash) and never the whole
source; the source project is not modified and not locked for writing.

Consolidate gains `used_only: bool`. It writes excerpts (with handles) of
just the ranges the timeline uses, for archiving. It defaults to off and
says how much space it will save before running.

Tests first (`tests/test_paste.py`):
- `test_pasting_into_a_project_that_has_the_media_copies_nothing`
- `test_pasting_linked_media_links_it_in_place`
- `test_pasting_converted_media_copies_only_the_range_plus_handles`
  (assert the new FLAC is under 10 % of the source size for a 2 s clip from
  a 60 s file)
- `test_excerpt_keeps_recorded_time_so_resync_still_works`
- `test_excerpt_transcript_words_line_up`
- `test_expand_excerpt_restores_the_full_media_exactly`
- `test_used_only_consolidate_keeps_every_clip_playable`

---

### WP21 — Several edits of the same material (versions)

Status: open. Needs WP1, WP4, WP8. Should land before WP18 is used in
anger, because cut decisions are shared between edits (below).

The use case: from one recording, a 1 × 60 min edit (*pistejulkaisu*) **and**
a 4 × 20 min mini-series (*minisarja*). These are five edits sharing
everything that is about the material and nothing that is about the cut.

| Shared by all edits of a project | Separate per edit |
|---|---|
| media store, linked files, FLAC working files | tracks, clips, buses, master |
| transcripts and their corrections | undo history (own tree per edit) |
| onsets, peaks, analysis caches | markers' accept/reject state |
| sync groups (they describe the recordings) | export settings |

Storage: one `project.sqlite`. `nodes` gets an `edit TEXT NOT NULL` column
and `meta` keeps one head per edit (`head:<edit id>`). A new table
`edits(id, name, created, archived)`. `History(path, edit_id)` opens one edit's
tree; nothing else in `History` changes. Migration: existing nodes become
edit `"main"`.

Session API:

```python
session.edits() -> list[dict]            # id, name, length, archived
session.switch(edit_id) -> Project       # engine and UI follow
session.new_edit(name, from_edit, range=None) -> str
    # copy of from_edit's current state; with range=(a, b), everything
    # outside [a, b) is ripple-deleted on all tracks, so the new edit IS
    # that part. One commit "created from <edit> <a>–<b>" in the new tree.
session.rename_edit(edit_id, name); session.archive_edit(edit_id)
    # archive hides; nothing is ever deleted
```

Making the mini-series: in the 60 min edit, set in/out around each part
and run "New edit from range" (Alt+Mod+N). Four times gives four edits,
each still pointing at the same media with the same sync groups.

**Cut decisions travel between edits.** Cut candidates (WP18) are anchored
to the recording, so a cut accepted in one edit can be recognised in
another: command `offer_cuts {from_edit}` lists every cut that is *applied*
in `from_edit` and whose audio is still present in this edit. In the
second-listen UI ([ / ] to step, Shift+Space to preview, Enter to apply,
Backspace to skip) each can be taken or left. Nothing is applied
automatically; the edits are different programmes.

Transcript corrections are shared at once: correcting a word in any edit
corrects it everywhere, because transcripts belong to the media.

UI: an edit switcher strip above the timeline (name, length), with
Mod+Shift+[ / Mod+Shift+] for previous / next edit and Alt+Mod+N for a new
edit from in→out (or a duplicate when no range). The history panel
shows the current edit's tree. Export has "all edits" (parallel, one file
each, named by edit).

Tests first (`tests/test_edits.py`):
- `test_new_edit_from_range_contains_only_that_range`
- `test_edits_have_separate_undo_trees`
- `test_edits_share_media_and_transcripts` (one import, two edits, no copy)
- `test_correcting_a_word_shows_in_every_edit`
- `test_offer_cuts_lists_cuts_applied_elsewhere_whose_audio_is_here`
- `test_offer_cuts_skips_cuts_whose_audio_is_not_in_this_edit`
- `test_archived_edit_is_hidden_but_restorable`
- `test_existing_single_edit_project_migrates_to_main`
- `test_crash_mid_edit_reopens_every_edit_at_its_own_head`

---

### WP22 — Track tags and ducking (what speechmix needs from the editor)

Status: backend done in v26.10.17.4 (track kinds, speakers, `duck_music` command); the UI for tagging tracks waits for WP4. Needs WP1, WP4.

The editor only has to say **what each track is**. Everything else speechmix
decides. `Track.kind` gets three values, chosen in the track header with a
one-key toggle (Alt+Mod+K cycles them on the focused track):

| Tag | Meaning | Used by |
|---|---|---|
| `speech` | one person's microphone | per-mic ducking and Auto-Silence (`analysis`), "who is talking", music ducking |
| `speech-mix` | several people in one file: a Zoom or phone recording | counts as "someone is talking" for music ducking and the transcript; **never** ducked or silenced per mic, because muting it would mute everyone |
| `music` | music beds, stingers, effects | ducked under speech |

`Track.speaker: str = ""` (default: the track's name) for the case where one
person's microphone is split across tracks: tracks with the same speaker are
one lane in the speech grid (`speechmix.timeline.Track.speaker` works the
same way). Stereo `speech` sources are averaged to mono for analysis, which
`analysis.track_levels` already does.

Import guesses the tag (mono: `speech`, stereo: `music`) and the user corrects
it. This is the only setup speechmix needs.

**Voice condition (R38), once speechmix has presets:** a sub-choice of the
speech tags, never a separate property. A track is `music`, or `speech` /
`speech-mix` with a condition `auto` | `clean` | `room` | `remote` | `phone`
(default `auto`); music tracks have no condition. In the track header it
reads as one choice: "Speech · remote". Alt+Mod+K cycles the kind; Alt+Mod+J
cycles the condition and does nothing on a music track. `auto` shows speechmix's suggestion
("suggested: remote, 3.4 kHz bandwidth") and needs one key to confirm. The
name goes to speechmix (WP10/WP23); kuulas holds no preset values itself.
Until the presets exist in speechmix, leave this field out.

**Ducking, both kinds, as editable automation (never baked in):**

- **Mics under each other:** `analysis.automix` (done) writes
  `speechmix.envelopes.duck_envelopes` as track automation on `speech` tracks.
- **Music under speech:** new `analysis.duck_music(p, store)` builds "anyone
  is talking" intervals from the `speech` and `speech-mix` lanes (the same rule
  as `nhsx.activity.speech_intervals`: pauses under `GAP_CLOSE_S` bridged,
  blips under `MIN_RUN_S` dropped) and, for each `music` clip, calls
  `nhsx.musicbed.curve(start, end, speech, cold_open=...)`. That is the bed
  shape measured from hand-made fades (rise, plateau, drop before the first
  word, cold-open level). Write the result as track automation on the music
  track. `cold_open=True` when the clip starts before the first speech in
  the programme.
- Mod+L (automix) runs both; each is also its own command.

Tests first: `test_speech_mix_tracks_are_never_ducked_or_silenced`,
`test_speech_mix_counts_as_talking_for_music_ducking`,
`test_tracks_with_the_same_speaker_are_one_lane`,
`test_music_automation_follows_nhsx_musicbed_curve` (compare to
`nhsx.musicbed.curve` directly on the same intervals),
`test_cold_open_bed_sits_under_the_first_words`.

---

### WP23 — FX layers: real-time where possible, rendered where not

Status: open. **Split in two** (owner wants R30 built first):
**WP23a** (MVP, ★): the layer model, tier 1 (real-time) and tier 2 (analyse
once, apply live), bypass, latency compensation, the CPU meter.
**WP23b** (phase 3): tier 3 (render), export waits for renders, and the
freeze-on-overload rule. The tests below are split the same way. Needs WP2, WP9. Extends WP10, which becomes tier 3 below.

Non-destructive effect **layers** on a clip, a track, a bus or the master,
shown as a stack in the inspector, each with bypass (B), reorder
(Alt+↑/↓), and a status chip. speechmix is an offline pipeline: some stages
need the whole file before they can decide anything (loudness measurement,
the rider's speech mask, lookahead limiting with a budget, de-bleed
estimation). So a layer is one of three tiers, and the UI shows which:

1. **Real-time.** pedalboard's own effects (high-pass, EQ, compressor,
   de-esser via `speechmix.chain` building blocks where they are causal,
   limiter) and VST3/AU plugins through `pedalboard.load_plugin` (as
   `speechmix.chain.load_plugin` does, e.g. dxRevive). Processed per block in
   the engine callback with state kept between blocks (`reset=False`), one
   instance per layer. Plugin latency: read the plugin's reported latency
   and compensate (delay every other path in the same bus by it); verify it
   once per plugin with `speechmix.chain.lag_samples`, because some plugins
   report it wrongly (see the comment in `chain.lag_samples`).
   Plugin windows open through `speechmix.editor` (child process) exactly as
   automixer does.
2. **Analyse once, apply live.** speechmix decisions that need the whole file
   but produce a gain curve: rider, mic ducking, music ducking, normalising
   gain, Auto-Silence. The analysis runs as a job when inputs change; the
   result is applied in real time as automation (already the model for
   ducking). Editable, and instant to play.
3. **Render.** Stages whose output is samples and that need the whole file
   (the full `chain.process` with de-bleed and budgeted limiting). The job
   renders a cached variant (WP10). While rendering, playback uses the
   tier-1 approximation if one exists (status "preview"), otherwise bypasses
   the layer (status "rendering"). When the render is ready, playback and
   export use it (status "ready").

**Full-stack playback (owner, 2026-10-18: later, not in the first version):**
listening to the whole mixed package inside kuulas, with the effects and
loudness normalisation applied, i.e. what export would produce. Built on tier 3:
the programme chain (`chain.process` and mastering) renders in chunks just
ahead of the playhead on spare cores, cached by content hash; playback uses the
rendered chunks where ready (status "mix preview") and the plain real-time mix
elsewhere. Phase 3, with WP23b.

**Where heavy restoration goes (owner, 2026-10-16):** dxRevive and the
speechmix voice chain probably cannot run in real time, so they are **never**
in the playback path:

- **Source-level layers** (restoration: dxRevive, de-noise, de-reverb, the
  voice chain) process each *media file* once, offline, in the background.
  The result is cached by content hash (media + plug-in + parameters +
  plug-in state + algorithm version). Every clip and every edit reuses it, so
  cutting, moving and trimming never re-render; only changed settings do.
  This is speechmix's own rule: what comes before the chain is baked in.
  - The render starts at the playhead and works outward, in chunks with
    overlap handles (reuse speechmix's parallel-piece machinery in
    `chain.apply_plugin`).
  - Playback uses processed audio where it is ready and the original
    elsewhere, with an "unprocessed" stripe on those stretches. Export
    waits for all of it.
- **Mix layers** (track, bus, master) are real-time only. A plug-in is
  allowed there only if a speed test on first use (10 s rendered at 4× real
  time or faster on one core) shows it can keep up.
- **Level audition** (Alt+Mod+L on a source layer): render a short window
  around the playhead (10 s, or in→out) at several values of the plug-in's
  own parameter (default 25 / 50 / 75 / 100), in parallel, through
  **speechmix's audition function** (requested from the podcast repo on
  2026-10-16; do not build it here). The window loops; **1–4** switch
  between renders instantly at the same position, **0** is the original,
  and switching is loudness-matched (speechmix meter). Changing settings in
  the plug-in's own window (speechmix.editor) re-renders the window in the
  background and swaps it in when ready. **Enter** keeps the setting, and the
  full source render starts. **Measured by the podcast repo (2026-10-18, dxRevive, one speaker, two 10 s
  windows):** the Mix parameter is a gain-preserving crossfade with dry weight
  a(m) = (1 − m)^2.37 (25 % = 0.50/0.50, 50 % = 0.20/0.80, 75 % = 0.04/0.96),
  not a plain blend. So the slider is `out(m) = a(m)·raw + (1 − a(m))·render(100 %)`:
  one render, instant, about −28 dB from the plug-in's own output (its own
  run-to-run noise is −25 to −38 dB, so separate renders per setting are less
  consistent than one render). Needs about 8 s of preroll before the window
  (about 2.6 s per 10 s render on one worker). Open: wet render delay of 0 to −3
  samples against the input; align the wet render to the raw per window.
  Needs `speechmix.mix_blend(raw, render100, m, wet_shift=None)` from the
  podcast repo (proposed there; do not build it here). The model (Studio or
  Studio 2) is in the plug-in state blob; Studio is 13 dB noisier.
- **Render in → out** (Shift+Mod+B, Logic's bounce in place): render the
  selected clips, or in→out on the selected tracks, through all their layers
  into new media (FLAC, content-addressed), with 2 s handles. The clips are
  replaced in one undoable step. The original media and layer settings are
  kept on the clip, so "un-render" restores them. Options: in place (the
  default), or to a new track with the original muted below. **Freeze
  track** is the same for a whole track.

**Playback and export stay identical:** export waits until every tier-3 layer
is ready (it shows what it is waiting for), and tier-1 layers run the same
code in export as in playback (block size independent: test it).

Budget: the engine measures callback time and shows CPU load. If a block
takes more than 70 % of its duration, freeze the most expensive real-time
layer (render it in the background as tier 3) and say so. Never let it
glitch silently.

Model: `Layer(id, kind, tier, params: dict, bypass: bool, state: str | None)`
in `Clip.layers`, `Track.layers`, `Bus.layers`, `Project.master_layers`.
Ops: `add_layer`, `set_layer` (coalesced for knob drags), `move_layer`,
`delete_layer`.

Tests first: `test_realtime_layer_output_is_block_size_independent`,
`test_plugin_latency_is_compensated_across_a_bus`,
`test_export_waits_for_rendering_layers`,
`test_bypass_is_bit_exact_passthrough`,
`test_overloaded_engine_freezes_the_heaviest_layer_and_reports_it`
(fake clock), `test_layer_params_drag_is_one_undo_step`.

---

### WP24 — Solo rules and A/B comparison

Status: level matching for A/B (`ab_match.py`) done in v26.10.18.1; 24.1 done in v26.10.16.2 (mixer rule and `ops.solo`; the coalesce
key is in `Session.edit` since v26.10.16.7, and the keys for WP5). 24.2 open. Part 1 needs only WP0, so do it right after WP0. Part 2 needs
WP4, WP21 and WP23.

#### 24.1 Solo (change to the existing mixer)

Workflow: mute everything, then solo one track at a time to listen.

- **Solo overrides mute.** A soloed track is heard even if it is muted.
  Today `mixer.mix` skips `track.mute` first; change the rule to
  `audible = track.solo if any_solo else not track.mute`.
- **Solo is exclusive by default.** New op `ops.solo(p, track_id,
  exclusive=True)`: soloing a track unsolos all others. Shift+S (and a plain
  click on S) is exclusive. Shift+Alt+S (and Mod+click on S) adds the track to
  the solo set or removes it. Soloing an already solo-only track again clears
  solo.
- A soloed track's bus is heard even if no track on another bus is soloed;
  a muted bus stays silent (mute on a bus is a deliberate send cut).
- Solo and mute changes are edits (they change what export renders), but
  they coalesce per track (`coalesce="solo"`) so clicking through tracks is
  not 20 undo steps.

Tests (red first against today's mixer):
`test_solo_overrides_mute`, `test_solo_is_exclusive_by_default`,
`test_additive_solo_keeps_the_others`, `test_resoloing_the_only_solo_clears_it`,
`test_muted_bus_stays_silent_under_solo`.

#### 24.2 A/B

One key, ` (backtick), toggles between A and B; the toolbar shows which is
playing. A comparison is set up from the palette or with these keys:

| Compare | Set up | Toggle does |
|---|---|---|
| **Two tracks** (two mics, processed vs. raw copy) | select two tracks, Alt+Mod+B | exclusive solo flips between them, playback continues |
| **Two edits** (WP21: 60 min vs. 20 min version) | Alt+Mod+B in the edit switcher with two edits selected | switches the open edit and puts the playhead on **the same audio** in the other edit (map timeline → recording clock → other edit's timeline, as markers do), then keeps playing. If that audio was cut in the other edit, it lands at the nearest kept point and says so |
| **Two takes** (WP19e) | on a take set | switches the active take in place (preview only, not an edit, until Enter) |
| **Layer settings** (WP23) | in a layer's inspector, "A/B" | each layer keeps an A and a B parameter snapshot; toggling swaps them live |

Fair comparison, following the no-level-surprises rule: **level-matched A/B
is on by default.** Measure each side's loudness over the
compared range (speechmix meter, mono-aware) and apply the difference as a
temporary gain on the louder side during the comparison only. Show the
offset ("B −2.3 dB matched"). Alt+` toggles matching off, to hear the real
difference.

A/B toggling is not an edit and never enters history, except when the user
commits a choice (Enter in take or layer A/B).

Tests: track A/B flips audibility without stopping the engine; edit A/B
lands on the same recording frame; level matching equalises two clips 6 dB
apart to within 0.3 LU; toggling writes nothing to history.

---

### WP25 — Music report (royalty reporting)

Status: partly done (v26.10.18.1: music tags editable and undoable via `set_music_info`; v26.10.16.15, v26.10.17.1, v26.10.17.2): report builder,
CSV (UTF-8 with byte-order mark, semicolons, formula guard) and HTML, tags
read at import, speech activity from the speech lanes, English and Finnish,
times in whole seconds rounded up, `Session.music_report` and
`GET /api/music-report`. **Open:** editing the tags (inspector), "all edits"
and "export alongside the audio", and the UI warning before export. Needs WP1, WP11, WP22 (music tags), WP21 (per edit), WP37
(the usage extractor: the report is its music-role view of an export).

Hindenburg's Music Report, done properly: for each edit, a list of every
piece of music the programme actually plays, for Teosto/Gramex-style
reporting.

- **Metadata at import:** read the file's tags with `ffprobe -show_entries
  format_tags` (title, artist, album, composer, lyricist, publisher, ISRC,
  label, copyright, year) into the media metadata. Editable in the
  inspector ("Music info"), stored per media and shared by all edits.
- **What counts:** clips on `music` tracks (WP22), excluding muted clips,
  muted tracks and stretches where the track's automation is below
  −60 dB (silenced, so not heard). Consecutive pieces of the same media
  with gaps under 2 s merge into one use.
- **Report rows:** order, title, artist, composer, publisher, ISRC, file
  name, programme in-time, out-time, duration used (hh:mm:ss), and whether
  it plays under speech (from WP22's speech intervals: "background" vs.
  "featured", which collecting societies often ask for).
- **Formats:** CSV (UTF-8, semicolon-separated so Finnish Excel opens it
  correctly) and a printable HTML table. One report per edit, or all edits
  at once (WP21). Export alongside the audio as an option.
- Missing title or artist is flagged in the report and in the UI before
  export, not discovered later.

Open question for the user (write it in ROADMAP.md): do Teosto or Gramex
want a specific file layout? If so, add it as a third format.

Tests first: `test_report_lists_each_music_use_with_programme_times`,
`test_muted_and_silenced_music_is_not_reported`,
`test_pieces_of_one_track_merge_across_short_gaps`,
`test_music_under_speech_is_marked_background`,
`test_missing_metadata_is_flagged`,
`test_csv_is_semicolon_separated_utf8`.

---

### WP26 — Fast listening and scrubbing

Status: the JKL key logic (`shuttle.py`: speed ladder, tape or grains) done in v26.10.18.1; engine skip list and tape-rate playback done in v26.10.18.21 (not yet heard); JKL keys and the speed chip done in v26.10.18.23; hold-K scrub and K-tap steps, scrub grains above 2x, pitch-kept fast listening (pedalboard chunk rendering, plan in the engine job report) and the UI open. Needs WP2, WP5.

**Sped-up listening (pitch preserved).** `.` toggles between normal speed
and *fast*. Fast defaults to 1.5× and can be set from 1.1× to 3× (Shift+. and
Alt+. step it up and down by 0.1). The toolbar shows the speed in a
coloured chip whenever it is not 1×, so nobody edits at 1.5× by mistake.

- Time-stretch with pitch kept, for speech: use pedalboard's
  `time_stretch` (Rubber Band) on overlapping chunks rendered **ahead** of
  the playhead in a worker thread: mix 2 s at 1× with `mixer.mix`, stretch,
  crossfade 50 ms into the previous chunk, queue it for the callback. The
  callback only reads the queue. Starting playback has up to 150 ms latency
  at non-1× speeds, and that is accepted.
- The playhead, transcript highlight and markers advance in *programme*
  time (they move faster), so everything stays in step.
- Editing keys work while playing fast; the D candidate key (WP18) uses the
  programme position.

**JKL shuttle and scrub (tape-style, pitch follows speed).**

| Keys | Does |
|---|---|
| L | play forward; each further L: 1.5×, 2×, 3×, 5× |
| J | play backward at 1×; each further J: −1.5×, −2×, −3×, −5× |
| K | stop |
| hold K + hold L / J | slow scrub forward / backward at 0.25× |
| hold K + tap L / J | step 10 ms forward / backward and play that 10 ms |

Scrubbing up to 2× is tape-style variable-rate resampling of the mix
(pitch moves with speed). That is how you find a cut point by ear, so do not
pitch-correct it. Above 2× it plays 60 ms grains with a skip between them,
so fast shuttle stays intelligible. Mouse scrub: dragging on the ruler
scrubs at the drag velocity, tape-style, with the same 2× switch to grains.
Skimming (WP19g) uses the same grain renderer.

**Making scrubbing feel immediate without a native engine** (allowed tactics,
in order of value; measure each before keeping it):
1. a background thread keeps about ±10 s of the finished stereo mix around
   the playhead in memory, so scrub grains resample from RAM and never run
   the mixer per grain (invalidate the cache on any edit);
2. a separate small-buffer output stream (256–512 frames) used only while
   scrubbing;
3. the playhead and waveform move with the pointer at once, and the audio
   follows;
4. extrapolate pointer or JKL velocity a few ms ahead when picking the grain;
5. cheap linear resampling while moving fast, proper resampling as it slows.

Engine API: `play(at, rate=1.0, preserve_pitch=True, until=None, skip=None)`
and `scrub(rate)` (continuous, negative = backward).

Tests first: `test_fast_playback_keeps_pitch` (a 440 Hz tone at 1.5× still
peaks at 440 ± 4 Hz); `test_fast_playback_advances_programme_time_by_rate`;
`test_chunk_joins_have_no_discontinuity` (no sample jump above the
signal's own maximum step at chunk boundaries);
`test_reverse_scrub_plays_the_mix_reversed`;
`test_scrub_above_2x_uses_grains`; keymap test for the JKL state machine
(L L L → 2×; K held + L held → 0.25×; release K → stop).

---

### WP27 — Project settings, changeable at any time

Status: open. Needs WP1, WP2, WP9, WP21.

A settings panel (Mod+,) for the open project. Every setting can be changed
later, and every change is an undoable edit like any other.

| Setting | Default | Notes |
|---|---|---|
| name | folder name | |
| sample rate | 48000 | 44100, 48000, 88200, 96000; see below |
| master | stereo | stereo or **mono** (for mono podcast delivery: the master sums L+R at −3 dB per side, so a centred mono voice keeps its loudness) |
| loudness target | −16 LUFS | used by export mastering (WP11) and match loudness (WP19c) |
| export defaults | WAV 24-bit | format, bit depth, stems on/off |
| fast speed | 1.5× | WP26 |
| marker reaction offset | 3 s | WP12 |

**Changing the sample rate later** (e.g. 44.1 → 48 kHz) is the hard one:

- The model counts frames at `Project.rate`, so the change is a pure op
  `ops.change_rate(p, new_rate)` that converts **every** position: clip
  starts and ends (convert the *edges*, not lengths, so adjacent clips stay
  adjacent), offsets, fades and crossfades (kept even), envelopes,
  automation, markers, sync origins and `Media.frames`/`time_ref`. Rounding
  goes to the nearest frame; source positions use the media's own ratio.
- Transcripts, onsets, BWF start times, sync origins and marker anchors are
  in flicks (docs/FORMAT.md), so they do **not** change; only edit state
  converts. That is why the format uses flicks.
- `MediaStore` keeps working files **per rate** (`m<id>.<rate>.flac`). A media
  that is linked PCM at the old rate becomes a resampled working file at the
  new rate (job, parallel, ffmpeg `aresample=resampler=soxr` when available).
  Old-rate files are kept, so undoing the rate change is instant and exact
  (history stores the old state, which still points at the old files).
- The engine reopens its output stream at the new rate.
- The UI shows progress while files convert. Playback waits for them, so it
  never plays the wrong rate.
- Recording (WP12) uses the project rate, so the settings panel says so.

Tests first: `test_rate_change_keeps_adjacent_clips_adjacent`,
`test_rate_change_moves_every_position_kind` (one fixture with clips,
fades, envelopes, automation, markers and sync origins, all converted within
one frame), `test_words_line_up_after_rate_change` (within 1 ms),
`test_undo_of_rate_change_is_exact_and_uses_the_old_files`,
`test_linked_pcm_gets_a_resampled_working_file`,
`test_mono_master_keeps_a_centred_voice_at_the_same_loudness`.

---

### WP28 — Focus mode: one track at a time

Status: open. Needs WP4, WP5, WP22. Sonnet 5.5. Decided by Opus from
`docs/OPUS-BRIEF.md`.

Focus changes what you **see**; solo changes what you **hear**. They are
separate, with one key that does both.

First version:

- **F** toggles focus on the focused track (the track the ↑/↓ cursor is
  on, WP5). **Esc** leaves focus. While focused, ↑/↓ moves focus to the next
  track, so you can walk through the tracks one at a time.
- **Speaker focus is the default unit.** Focusing a track focuses every track
  with the same speaker (WP22), so one person's split tracks expand together.
- **Auto-shrink:** the focused lanes take all the remaining height; every
  other lane shrinks to a 16 px strip showing its name, its half waveform and
  its clip edges. Sync stays visible at a glance. The shrink animates over
  120 ms, or instantly under `prefers-reduced-motion`. A setting turns
  auto-shrink off (then focus only highlights the lane).
- **Shift+F** focuses and solos (exclusive, WP24.1). Leaving focus restores
  the solo set as it was before; focus remembers it.
- **The transcript follows focus:** other speakers' words are dimmed, not
  hidden, so the conversation still reads. A toggle (Alt+F) hides them
  instead.
- **The focused track's automation** (ducking, gain) is drawn as an editable
  band under its waveform at a readable height, so ducking can be corrected in
  place.
- "Focus on a clip" is not a new feature: Mod+H (zoom to selection) with focus
  on already gives it.

v2 (parked in ROADMAP.md): a focus history stack (back to the previous
focus), and focus that follows whoever is talking during playback.

Focus, the remembered solo set and the lane heights are UI state: never in
history and never in the project file.

Tests (pure functions, `node --test`): lane layout given focus (heights sum
to the viewport; strips 16 px; focused lanes share the rest), speaker focus
expands every track of the speaker, Shift+F then Esc restores the previous
solo set, ↑/↓ in focus moves focus.

---

### WP29 — Project format v1: package, material, versions, backups

Status: done in v26.10.16.5. Needs WP0. **Opus 5.5.** Build it **before WP1**, so the
Session is written against the final layout. Spec: `docs/FORMAT.md`
(everything in it is in scope except WP30's clock change).

- `src/kuulas/package.py`: create and open `Name.kuulas`, write the manifest
  atomically, enforce the reader rules, take and refresh the lock (read-only
  open when another live host holds it), run migrations with a pre-migration
  backup, take automatic backups on a timer with the retention rule.
- `History` moves to the v1 schema: `blobs` (content-addressed states),
  `edits`, `nodes` with `edit`, `op`, `context`, `material_from/to`. States
  are stored once per hash.
- **Material** moves out of edit state: `media` rows, `media_paths`,
  `transcript_revs`, `material_revs` with a versioned root, and undo of a
  material step with the conflict rule from FORMAT.md.
  `Project.transcripts` is removed from the edit model.
- `MediaStore` keeps its files but writes metadata as `media` rows (the row
  is the "import finished" marker) and caches under `caches/`, keyed as
  FORMAT.md says.
- Every model dataclass gets `extra: dict`, and unknown keys round-trip.
- Migration v0 to v1 for folders made by today's code (FORMAT.md, last
  section), with a fixture.
- Log the database size on open; `kuulas info <folder>` prints manifest,
  sizes, media states (linked, working, missing) and backup count.

Tests first:
`test_new_package_has_manifest_lock_db_media_caches`,
`test_manifest_is_written_atomically` (crash simulated between temp and
rename leaves the old manifest), `test_newer_min_reader_refuses_with_version`,
`test_newer_version_opens_and_keeps_unknown_keys` (unknown keys in a state,
a media row and a table survive a save), `test_live_lock_from_another_host_opens_read_only`,
`test_stale_lock_is_taken_over`, `test_identical_states_are_stored_once`,
`test_step_ids_are_uuid7_and_record_author_and_machine`,
`test_material_undo_refuses_after_a_later_material_change`,
`test_transcript_correction_is_seen_by_every_edit`,
`test_backup_retention_keeps_12_recent_and_one_per_day`,
`test_backup_never_writes_the_live_file`,
`test_migration_v0_to_v1_keeps_every_state_media_and_transcript`,
`test_caches_can_be_deleted_and_are_rebuilt`,
`test_measured_state_size` (the FORMAT.md fixture stays under 30 KB
compressed per step; fails loudly if the model bloats).

---

### WP30 — Recording clock in flicks; sync per media

Status: done in v26.10.16.6. Needs WP29. **Opus 5.5.** Before WP1, after WP29.

- `src/kuulas/clock.py`: `FLICKS = 705_600_000`, exact conversions
  `frames_to_flicks(frames, rate)` and `flicks_to_frames(flicks, rate)`
  (round half to even, documented), and a check that a rate divides FLICKS
  (all supported rates do; refuse others at import with a clear message).
- `Media.time_ref` becomes `time_ref_flicks`. Transcript words, onsets and
  marker anchors are stored in flicks from the media's start;
  `transcribe.parse` and `from_segments` produce flicks; `transcript.timeline_words`
  converts at read time.
- Sync groups move to material, per media: `{main, members: {media:
  origin_flicks}}`. `Clip.sync` and `Clip.sync_origin` are removed.
  `ops.mark_in_sync` and `ops.resync` keep their behaviour and every existing
  sync test (they must pass unchanged, apart from the setup that creates
  groups), now reading membership from material.
- Migration: existing clip sync fields become per-media members
  (FORMAT.md, migration step 4). If two clips of one media had different
  origins, keep the main clip's piece's value and log a warning.

Tests first: all of `tests/test_sync.py` unchanged in behaviour;
`test_flicks_are_exact_for_every_supported_rate` (round trip frames to
flicks to frames is identity for 8k to 192k); `test_rate_change_leaves_words_untouched`;
`test_bwf_time_reference_is_stored_in_flicks`;
`test_excerpt_inherits_its_originals_sync_origin`.

---

### WP31 — Changes view and checkpoints

Status: the diff (`changes.py`, audible ranges per recording) done in v26.10.17.9; the panel, checkpoints, gain/mute/take changes open. Needs WP8, WP18 (recording-clock anchoring), WP21. Sonnet 5.5.

Compare any two points: two history steps, a checkpoint, or two edits.

- **Checkpoints:** **Mod+S** saves a named version (named by time, renameable),
  **Shift+Mod+S** asks for the name first (WP5); exports add one too (WP11). Checkpoints are ledger entries
  (`checkpoints` table, docs/FORMAT.md) shown pinned in the history panel.
- **Diff:** for each sync group (or media), the recording ranges present in A
  and not in B (removed), in B and not in A (added or restored), and
  ranges whose gain, mute, ducking, FX or take differ. Pure function
  `changes.diff(state_a, state_b, material) -> list[Change]`, each with
  recording anchors and both sides' timeline positions.
- **UI:** "Compare with…" (Alt+Mod+D) picks the other point. The timeline
  shows removed audio as red gaps, added audio highlighted and level changes
  marked; the transcript strikes removed words. **]** / **[** step through
  changes; **Shift+Space** plays each with 2 s before and after (the
  WP18 preview); **`** flips A/B at that spot (WP24.2).

Tests first: `test_diff_of_a_ripple_cut_is_one_removed_range`,
`test_diff_survives_unrelated_later_edits`, `test_restored_range_shows_as_added`,
`test_gain_and_take_changes_are_reported`, `test_diff_between_two_edits_uses_recording_ranges`.

---

### WP32 — Review round trip: send, suggest, receive, decide

Status: open. Needs WP29 (UUID steps, checkpoints, copies), WP31. **Opus 5.5**
(merging diverged copies). Spec: docs/FORMAT.md, "Review round trips".

- **Settings:** your name (author on every step), and initials and colour
  shown on suggestions.
- **Send for review** (Mod+Shift+E): pick the person, a note, and media
  (used ranges plus handles by default; or none to relink by hash; or
  everything). It writes a `sent` checkpoint and the hand-off copy.
- **Suggest mode** (Mod+Shift+S toggles; a "Suggesting as Ville" banner while
  on): edits of the conditional kinds become suggestions instead of changes.
  Other edits are refused in suggest mode, with a message saying they can be
  made unconditionally after leaving suggest mode.
  Suggestions draw as dashed overlays in the author's colour, and the
  transcript shows suggested cuts struck through in that colour.
- **Receive** (open the returned copy, or "Import changes from…"):
  - If A's head is still the `sent` checkpoint, the history simply
    continues.
  - If A has edited since, B's unconditional changes become suggestions too,
    via the WP31 diff, and B's steps are kept as a branch.
- **Review panel:** "Done by Ville (12)" and "Suggested by Ville (7)". Every
  item can be previewed (Shift+Space), flipped A/B (`) and accepted
  (Enter) or rejected (Backspace). Done items can be reverted, which is the
  same as rejecting. Each item shows B's note. A summary line reads
  "7 of 19 left".

Tests first:
`test_suggest_mode_records_cuts_as_suggestions_not_changes`,
`test_accepting_a_suggestion_is_an_undoable_step_by_the_reviewer`,
`test_suggestion_still_applies_after_unrelated_edits`,
`test_unchanged_sender_continues_history_with_reviewers_steps`,
`test_diverged_sender_gets_reviewers_changes_as_suggestions`,
`test_step_ids_never_collide_across_copies`,
`test_handoff_with_used_ranges_copies_only_excerpts`,
`test_handoff_without_media_relinks_by_hash`.

---

### WP33 — Internationalisation foundation (i18n)

Status: WP33a done in v26.10.16.4 (Python: catalogs, `messages.t`, error shape,
speechmix translator, literals converted); WP33b done in v26.10.16.12
(`ui/i18n.js`, `GET /api/locales/<lang>`, AppleLanguages, UI scans; the
language setting's screen waits for WP27). **Split in two**, so no
WP writes untranslated text:
- **WP33a** (Python: catalogs, `messages.t`, API error shape, speechmix
  translator, converting today's literal messages in `ops`, `media`,
  `transcribe` and `analysis`). Needs WP0. Haiku 5.5. **Before WP29.**
- **WP33b** (UI: `ui/i18n.js`, `Intl` formatting, key names, the language
  setting, the UI literal-text check). Needs WP3 and WP33a. Sonnet 5.5.
  **Before WP4.**

English is the source language; Finnish is complete from day one.

Left over from WP33a, done in WP33b: on macOS a Terminal session usually
has `LANG=en_US.UTF-8` even when the system language is Finnish, so
`messages.default_language()` should read the system's language list (`defaults read -g
AppleLanguages`) before `LANG`. And the `ast` check covers raised exceptions
only; returned user-facing text is checked by review.

- **One catalog for both sides:** `src/kuulas/locales/en.json` and `fi.json`.
  Keys look like `edit.split.label` and `error.media.missing`, and values
  use `{name}` placeholders. Plurals are objects of
  CLDR categories, e.g. `{"one": "{count} clip", "other": "{count} clips"}`.
  Python reads the files directly; the UI loads `GET /api/locales/<lang>`.
- **Python:** `kuulas.messages.t(key, **values)`, modelled on
  `speechmix.messages`. It never raises: an unknown key or a missing value
  falls back to English, then to the key itself, because messages are made on
  error paths. API errors return `{"error": {"key", "params", "text"}}`, with
  `text` in the session's language.
- **speechmix's messages too:** kuulas registers its translator with
  `speechmix.set_translator`, and kuulas's `fi.json` carries the Finnish of
  speechmix's keys (`speechmix.messages.FALLBACK`), so pipeline errors
  appear in Finnish. A test fails when speechmix adds a key that kuulas has
  not translated. Long term those Finnish strings belong in speechmix itself
  (autoraffkat's `i18n.py` has them too); note it for the podcast repo.
- **UI:** `ui/i18n.js` with `t(key, values)`, plural rules from
  `Intl.PluralRules`, and number, date and time formatting through `Intl`,
  following the UI language:
  - decimal comma in Finnish: "−2,5 dB", "12:34,567";
  - absolute times in Helsinki time with the zone named (the owner's rule):
    "19.45 (Helsinki)" in Finnish, "7:45 pm Helsinki" in English;
  - key names per platform and language: ⌘ on a Mac, Ctrl elsewhere;
    "Välilyönti" / "Space".
- **Language setting:** defaults to the OS or browser language, falls back
  to English, and is changeable in settings (WP27) without a reload.
- **Not translated:** recorded content. A transcript's language is a
  property of the media (Whisper's language), not of the UI.
- **Checks** (tests, so lint-strength):
  - `en` and `fi` have the same keys and the same placeholders in each value;
  - every `t("…")` key used in `src/` and `ui/` exists in `en.json`;
  - no UI module assigns a string literal containing letters to
    `textContent`, `innerHTML`, `title`, `aria-label` or `placeholder`, and
    no Python module raises or returns a user-facing message without `t()`
    (scan with `ast`).

Tests first: `test_catalogs_have_identical_keys_and_placeholders`,
`test_unknown_key_falls_back_to_english_then_key`,
`test_missing_value_never_raises`, `test_speechmix_messages_are_translated`,
`test_every_used_key_exists`, `test_no_literal_ui_text` (node),
`test_finnish_decimal_comma_and_helsinki_time` (node).

---

### WP34 — Import hardening

Status: done in v26.10.16.9. Decoder timeouts (probe 20 s, decode stall 120 s)
are not measured yet; the 4 GB RF64 path is checked with a sparse file only. Needs WP1. Sonnet 5.5. In M1.

Ground rule 13 for everything that brings audio in (`MediaStore`,
`Session.import_media`):
- Probe before decoding (soundfile or ffprobe) with a timeout; decode with a
  timeout; kill a hung decoder.
- Import what decodes: a truncated or damaged file comes in as far as it
  goes, marked partial ("41:03 of 58:00") with a warning.
- One bad file never fails a batch; the report names each failure and why.
- Free-space check before decoding (estimate from duration and channels);
  a full disk mid-import removes the partial file and says how much space is
  needed.
- More than two channels: downmix to stereo with a warning (choosing
  channels is a later option). 32-bit float, VBR MP3 and other formats
  without exact seeking are decoded fully to FLAC. A video without audio, an
  empty file, or a silent file is refused or flagged with a clear message.
  BWF time references outside a sane range (more than 24 h) are ignored
  with a warning. RF64 WAVs over 4 GB work.
- A source on a drive that disappears mid-import: the partial file is
  removed and the error names the drive.
Fault-injection fixtures in `tests/fixtures/broken/`: truncated WAV, garbage
header, zero-length, MP3 with junk in the middle, video without audio,
6-channel WAV, nonsense BWF time.

---

### WP35 — Remembered settings, quick actions, view memory

Status: first version done in v26.10.18.24 (view memory per project, user-preference helper, Recent commands, reset command); panel sizes (no resizable panels yet) and per-dialog last values open.

- **Where things are remembered** (ground rule 16): user settings
  (`platformdirs` user config dir: `~/Library/Application Support/kuulas`,
  `%APPDATA%\kuulas`, `~/.config/kuulas`), project settings (WP27), a
  user's view of a project keyed by the manifest `id` in the user config dir
  (close and wide zoom, lane heights, panel sizes, scroll, current track,
  follow mode, last open edit; never in the project folder), per-dialog last
  values (export, import, transcribe, send for review, render, audition, new
  edit from range, consolidate), and per-media choices (transcript language,
  voice condition, chosen plug-in level) in the project.
- **Quick actions:** the plain key runs with the remembered settings;
  Alt + the key, "…" on a button, or "Change…" in the result message opens
  the dialog. The first time (nothing remembered) the dialog opens. Hovering a
  command shows its current defaults ("Mod+E · MP3 128 kbps, mono").
  Presets are commands, bindable to keys.
- **Safety resets on open:** group editing on (with a message if it had been
  off), recording not armed.
- **Helpful messages:** every action reports what it did with Undo and,
  where relevant, Change…; errors say how to fix; first-run hints appear
  once per feature; the palette lists recent commands first and shows keys.
- **Guessed defaults** with no history: mono master for all-mono speech; the
  MP3 bitrate from the master's channels; transcript language detected.

Tests: settings round-trip per scope; a view restored on reopen; quick
action runs without a dialog when settings exist; the safety resets; a
dialog shown twice in a row with identical answers fails a UI test.

---

### WP36 — Caches per recording

Status: done in v26.10.16.10, except the scrub mix cache (needs WP26, WP31)
(the decoded-chunk cache moved under the budget in v26.10.17.2).
Envelope composition is exact on a 60-frame grid; after a cut at another
frame one hop can be off at a hard edge (95th-percentile error under 0.5 dB,
silence edges within one 20 ms hop). A vanished linked file is noticed at the
next `missing()` check, not on read: the background check must call it. Needs WP1. Sonnet 5.5. Before WP4.

Ground rule 15, concretely:
- **Peak pyramid** at import: min/max per 256, 1024, 4096, 16384 and 65536
  frames, in `caches/peaks/`, keyed by media sha256 and algorithm version.
  Served as binary tiles (`GET /api/peaks/{media}/{level}/{tile}`) with an
  `ETag` of the key and long cache headers, so the browser keeps them.
- **Level envelopes per media** (20 ms hops, as speechmix measures):
  `analysis.track_levels` composes the timeline from cached per-media
  envelopes instead of re-reading audio after each edit. The result equals
  today's (test), and an edit no longer triggers any audio read.
- **Memoized derived views:** timeline words, candidate positions and sync
  partners, keyed by (edit-state hash, transcript revisions).
- **Decoded states:** History keeps the last 64 decoded states in memory,
  so undo and redo never decompress.
- **Scrub mix cache** (WP26) invalidates only the changed ranges of an edit
  (WP31's diff).
- **One memory budget** for all caches (default 2 GB, settable), LRU,
  spilling to `caches/`; hit rates logged.

Tests: an edit causes zero media reads in analysis; the pyramid tile at
each level equals a direct min/max; cache eviction respects the budget;
undo of the last 64 steps does no decompression.

---

### WP37 — Usage extractor (shared by music report, series, changes view)

Status: done in v26.10.16.14. Needs WP30. Sonnet 5.5.

`src/kuulas/usage.py`: from one project state (and material), list every
used stretch of every recording: `Use(media_sha256, from_flicks, to_flicks,
timeline_from, timeline_to, track, role, audible)`, where `audible` is false
under a muted clip or track, or where the track's automation is below
−60 dB. Excerpts (WP20) map back to their original's sha256 and recording
clock. Adjacent uses with gaps under 2 s merge (a parameter).

Consumers: the music report (WP25: the music-role view of an export), the
series usage files (WP38), and the changes view's diff (WP31: the
difference of two states' uses).

Tests: uses of a cut-up clip map to the right recording ranges; muted and
ducked stretches are inaudible; excerpts map to the original; merging across
short gaps; the result is identical for the same state (stable ordering).

Implementation: `src/kuulas/usage.py` exposes `extract(project,
merge_gap=2*FLICKS) -> tuple[Use, ...]`. Automation is split at integer-frame
crossings of −60 dB; the threshold itself remains audible. Excerpt chains map
to their root media hash and sum their recording-clock origins. Ranges merge
only when source and timeline gaps are both below the limit and the track,
role and audibility match. Invalid media references and excerpt cycles raise
translated `UsageError`s.

---

### WP38 — Series: material reused across episodes

Status: open. Needs WP37, WP21, WP20, WP39. Sonnet 5.5.

A **series** is a folder that projects belong to (owner, 2026-10-16):

```
Series name/
  series.json                  name, id, member project ids and paths
  usage/<project id>.json      what that project uses, written only by it
```

- **Files live anywhere** (owner's choice). The series points to recordings
  and does not own them. Recordings are matched by sha256.
- The manifest gets `series: {id, path}`. "Join series…" and "Leave series"
  are commands.
- Each project writes its **own** usage file atomically on every save and on
  close: per edit, the WP37 uses of its current state, and per export the
  uses of that export. One file per project, never a shared database, so two
  machines and a sync folder cannot corrupt each other.
- **Published only when marked** (owner: "surely this is the final export"
  never is): an export becomes *published* when the user marks it so
  (command "Mark as published…", and unmark). Until then its uses count as
  draft.
- **Badges, never dialogs:** a clip whose recording range is used by another
  project shows "also in Ep 3 (published v2)"; hover lists where. Bringing
  material in (paste, bin, import) shows the same note inline.
- **Series view:** each recording as a bar with the stretches used per
  episode coloured (published or draft) and unused material visible; click
  to open that episode at that spot. Transcript search across the series
  with usage marks.
- **Season music report:** WP25 across all episodes of the series.
- Music reuse ("this track is also in Ep 2") uses the same badges.

Tests: usage files are written atomically and only by their own project; a
closed project's uses are visible to an open one; published vs draft; an
excerpt counts as a use of its original; two machines writing their own
files never conflict.

---

### WP39 — Portable projects: different paths on every machine

Status: done in v26.10.16.14 (resolver, media folders, learned rewrites, single-file relink; docs/FORMAT.md updated; schema v3; not tried across two real machines). Needs WP29. Sonnet 5.5. Before WP32 and WP38.

User A works on a project, hands it to user B, whose paths differ; it must
still work (owner, 2026-10-16).

- Each linked media row stores, besides the absolute path, the path
  **relative to the project package** and **relative to the series folder**
  (if any) (docs/FORMAT.md, "Portability").
- **Resolving a missing file** tries, in order: relative to the project;
  relative to the series folder; the user's **media folders** (a per-user
  setting, e.g. `~/Dropbox/Kapina`), searched by sha256 with a size
  prefilter; then remembered paths. A file counts only if its content
  hash matches.
- **Relink once, everything follows:** when the user points to one missing
  file, kuulas learns the path rewrite (e.g. `/Volumes/Raid/Kapina` →
  `~/Dropbox/Kapina`), applies it to all other missing files, verifies each
  by hash, and remembers the rewrite per user.
- On open, the resolution runs in the background; clips that are still
  missing are drawn offline, and one message offers "Find missing files…".

Tests: a project copied to another root with a different absolute path
opens with all media found relatively; media folders are searched by hash;
one relink fixes the rest through the learned rewrite; a same-named file
with different content is never used.

---

### WP40 — Long history stays fast

Status: first step done in v26.10.17.4 (paged history, scale tests); the History panel waits for WP4. Needs WP29, WP8. Sonnet 5.5.

Owner, 2026-10-16: disk space is not a worry; performance is. Keep every
step forever, and make history length irrelevant to speed:
- Budgets, tested on a generated 5,000-step history: open under 1 s; undo
  and redo constant time; a history-panel page (paged SQL, windowed tree
  layout) under 50 ms; an edit's cost independent of history length.
- **Incremental backups:** since states are immutable and content-addressed,
  a backup appends only new rows to the backup database; it runs as a
  low-priority job, never while playing or editing; a full snapshot on close.
- **Thinning is a safety valve only:** it runs only if one of the budgets
  above is measured to fail. It then follows FORMAT.md's restic-style rule:
  every step for the last 14 days of working time, then one per hour of work,
  then one per working day. It never thins versions, exports, review copies,
  session markers, branch tips or material steps, and it always backs up
  first.

---

### WP41 — People, interviews, who speaks (data model)

Status: done in v26.10.16.13. Usage marks on passages wait for WP37/WP38. Delete commands for people and interviews: v26.10.17.2. Needs WP30. Sonnet 5.5. **Before WP7 and WP9**, so transcripts
are linked to people from the first one (owner, 2026-10-16).

Build docs/FORMAT.md "People, interviews and bits" for people, interviews,
`media.person`, the speaker-label map and `person` on stored words (bits are
WP42). Session commands: create and edit people and interviews; assign a
file's person; map speaker labels to people; import offers "this is one
interview" for files imported together (defaults from WP1's sync group).
Series storage: one JSON file per item, atomic writes, conflict copies
detected. Queries: `passages(person)` returns every transcript passage by a
person across the project or series, with recording ranges, ready for the
WP38 usage marks. All material steps are undoable. Messages in en and fi.

Tests: a mic file's words carry its person; a mix's labels map to people,
and remapping changes no stored word text; one interview links three files
from different recorders; series items survive two writers editing different
items; a conflicted item is reported; passages by person span projects in a
series.

---

### WP42 — Bits and the index-card view

Status: open. Needs WP41, WP38, WP20, WP4, WP7. Sonnet 5.5. Phase 3.

Scrivener-style planning across a series (owner, 2026-10-16):
- **Bits** (docs/FORMAT.md) are made from a transcript selection ("Make
  bit", key K in the transcript), from a cut candidate, or by hand. Each has a
  title, summary, people, tags, status and colour.
- **Card view:** one column per episode (edit) plus an "unplaced" column.
  Drag a card into an episode to add it to that episode's outline; the order
  of cards is the outline. Keyboard: arrows move between cards, Mod+arrows
  move a card, Enter opens it, Space plays it.
- **Assemble:** builds or updates the episode's timeline from its outline,
  as clips with 2 s handles, using WP20's paste machinery. Cards already
  placed are not duplicated, and the result is one undoable step.
- **Person view:** everything a person said across the series
  (`passages(person)`), with usage marks (WP38). Select and press K to make a
  bit, or drag it to an episode column.
- Cards show their usage ("used in Ep 3, published v2").

Tests: a bit covers every mic of its interview; assembling twice adds
nothing new; card moves are undoable; the person view lists passages across
projects with correct usage marks.

---

### WP43 — Narration placeholders

Status: first version done in v26.10.18.22 (placeholders in the edit state, ops, replace with a take, script export, export warning, T key and prompt); the "to record" row in the transcript and an in-app recorder open. Needs WP4, WP5, WP7. Sonnet 5.5. Phase 2. The data model
part (a placeholder clip kind) can land with WP41 or earlier.

Script text for narration that has not been recorded yet (owner, 2026-10-16):
- **Model:** a clip with `kind="placeholder"`, no media, and `text`,
  `narrator` (a person, WP41), `wpm` (speaking rate) and `length`. The
  length is estimated from the text at the narrator's rate (default about
  2.3 words per second, to measure on the owner's own narration) until the
  user drags it. Placeholders live on a narration track and obey the
  edit-target rule; the mixer plays them as silence.
- **Keys:** T inserts a placeholder at the playhead and opens its text;
  Alt+T previews it with the system's speech voice (macOS `say`, Windows
  SAPI via the standard OS API), never exported.
- **Transcript:** placeholder text appears inline, in italics, marked "to
  record", so the episode reads as a script.
- **Recording it:**
  - "Export narration script": placeholders in order, with the line
    before and after for context;
  - in record mode (WP12) the next placeholder's text shows on screen, and
    the take replaces it;
  - importing with a placeholder selected replaces it.

  Replacing adjusts the timeline to the real length, as one undoable
  time-shifting edit.
- **Cards:** narration cards in WP42's outline.
- **Export guard:** unrecorded placeholders are reported before export
  ("3 narration placeholders not recorded · Export anyway · Show them").

Tests: estimated length from text and rate; a placeholder plays silence;
replacing with a take ripples the later material by the difference, on the
group's tracks; the script export lists placeholders in order with context;
the export guard counts unrecorded placeholders.

---

### WP44 — Auto-Silence as merged gate ranges

Status: backend done in v26.10.18.5 (`gate.py`, `Track.gate`, ops, the mixer ramp, audibility everywhere, format version 3 with `min_reader` raised per project); gate bands and "Open this stretch" in the editor done in v26.10.18.7 (a per-lane toggle and a context menu are open) (owner decision 2026-10-17: "measure the need to mute very often,
but the muted region should be merged"). Needs WP1. Sonnet 5.5. Do it before the
soft-cut work (cut-keeping-the-gap, see the architect's note in the session log
and the open questions in `docs/handoffs/`), and before any long-session use.

**Problem.** `analysis.auto_silence` calls `ops.mute_ranges` for every closed
stretch, and each call splits the clip. A 1-hour 4-mic conversation gives
thousands of pieces (an estimate: 5,000 to 10,000; measured 69 ms to pack a state
at 8,000 pieces, over the 50 ms edit budget, and about 119 KB per history step).

**Rule.** The measurement stays fine (hop by hop, every mic against the others,
bleed included). The result is **merged**:
1. In `silence_ranges`, after combining "no talk" with the ducked (bleed) mask,
   close every open stretch shorter than `MIN_OPEN_S` (start with 0.4 s) and drop
   every closed stretch shorter than `MIN_CLOSED_S` (start with 0.3 s). Constants
   live next to `OPEN_BEFORE_S`; tune them on the fixtures and write the values
   and the reason in the module.
2. **Store the result as a gate, not as clip pieces:** a new field
   `Track.gate: tuple[tuple[int, int], ...]` (frames, sorted, non-overlapping,
   merged), part of the edit state, so history keeps it. Clips are never split by
   Auto-Silence. `ops.set_gate(p, track_id, ranges)` replaces a track's gate (one
   undo step); `ops.add_gate_range` and `ops.remove_gate_range` merge or split
   correctly (removing a range from the middle of a gate range gives two).
3. The mixer applies the gate with a derived 30 ms ramp at each edge (computed in
   the mixer, not stored), in `_track` and `track_stem`, so playback and export
   agree. `usage.extract`, `music_report`, `transcript.timeline_words`,
   `analysis.track_levels` and the onset/edge points treat gated frames as
   inaudible, as they do for muted clips today.
4. Running Auto-Silence again replaces the track's gate (no pile-up).
5. Old projects: no gate means an empty gate. Old projects that contain
   Auto-Silence clip pieces keep working unchanged. FORMAT.md gets the field
   and a version bump (`min_reader` unchanged: an old reader keeps the field in
   `extra` and ignores the gate, which is audible, so decide with the owner
   whether `min_reader` must go up; flag it, do not guess).
6. UI: gated ranges are drawn as dim bands over the lane (not hatched clips),
   a lane toggle shows or hides them, and clicking a band offers "Open this
   stretch" (`remove_gate_range`).

**Tests, first.** Fragment count on a synthetic 1-hour four-voice conversation
stays under a fixed budget (decide it from the fixtures; the point is orders of
magnitude fewer than one per bleed toggle); packing the state with the gate stays
under 50 ms; export equals the old clip-piece export within the ramp (compare
against `mute_ranges` output on a short fixture); undo restores the previous gate;
re-running does not pile up; a clip edit across a gated range keeps the gate in
time (a ripple delete shifts or trims gate ranges like automation points); the
gate survives save and load; the mixer applies the ramp exactly once.

---

### WP45 — Compare: non-destructive previews and A/B by listening

Status: open, design in progress (owner request 2026-10-17: "various
non-destructive previews and A/B tests; I pretty often want options; I need a
way to quickly compare them by listening"). Needs WP2, WP5; builds on WP24.2
(A/B of tracks and edits), WP18 (candidate preview), WP19e (takes), WP21
(versions), WP10 (voice presets), WP23 (FX layers). Opus for the engine part,
Sonnet for the UI.

One concept, not several: a **comparison** is a scope (a range, a track, the
whole edit) plus two to four **variants**, each a provisional layer on top of
the project, never committed while comparing. Variants: with or without a cut, a
value against its default (see the double-click toggle), two tracks, two takes,
two edits, a history step before and after, a voice preset or an FX layer on or
off, a loudness-matched pair.

- **Engine.** A variant is rendered as an alternative source for the compared
  range; switching keeps the playhead position and crossfades 10 to 30 ms, so a
  flip is click-free. Real-time variants render on the fly; offline-only ones
  (dxRevive, the voice chain) are rendered first and show progress per slot.
- **Level match on by default**, using the `ab_match` gains (O3): a louder
  variant always sounds better, so the trim is applied and shown; switchable off.
- **Blind mode**: slots shuffled and unlabelled until the choice is made.
- **Decision**: "Keep this one" commits that variant as one undoable step and
  discards the rest; Esc discards the comparison and leaves the project
  untouched.
- **Loop**: the compared range by default, plus 2 s each side.
- **Tests, first:** switching preserves the playhead position; no commit happens
  while comparing (the history head does not move); keep commits exactly one
  step; Esc leaves the project byte-identical; the level trim equals
  `match_gains`; blind shuffling is stable within a comparison and hidden labels
  are revealed only after the choice.
- **UI design** is in `docs/design/GUI-DESIGN.md` once the designer has added
  the Compare screen.

---

### WP46 — Clipboard with history

Status: first version done in v26.10.18.11 (entries, history file, paste planning, copy/cut/paste commands and keys, Clipboard tab, sync-group aware insert); a play-preview of an entry, lift-cut and clipboard sharing between windows open (owner request 2026-10-18: "we need an EXTENSIVE clipboard, with
history"). Needs WP1, WP4, WP5. Replaces and extends WP20 (paste without bloat).
Sonnet for the logic, Opus review of the data model.

Cut (X) copies to the clipboard and removes with ripple; Delete (Backspace) is a
soft cut that leaves the gap and never touches the clipboard; Copy (Mod+C) copies
only. Every copy or cut makes a **clipboard entry**: a snapshot of the selected
clips or range across tracks, kept as references (media hash, offset, length,
gain, pan, fades, envelope, the clips' relative layout), never as audio, so it
costs nothing. Entries are kept in a history list (a "Clipboard" panel tab) with
a preview (play it), a name (automatic, editable), pin, delete, and "paste again".
Paste has four forms: insert at the playhead (ripple), overwrite, paste on the
same tracks, paste on the current track. Entries survive restarts, are stored
per user and can be pasted into another open project (media are then linked, see
the selective import from another project). The data model, the 'what is copied
from a sync group' rule (WP19a) and the limits (how many entries, how long) are
decided in the design pass.

---

### WP47 — Panel arrangement

Status: open (owner, 2026-10-18: later). After the density work. Three slots (right
sidebar, bottom dock, optional left sidebar); drag a panel tab into another slot;
layout presets (Editing, Transcript first, Mixing); remembered with the other
settings (WP35). No floating windows in the browser; the desktop wrapper (WP15) may
add them later.

---

### WP48 — Contextual help (from v1) and onboarding (later)

Status: contextual help done in v26.10.18.9 (help panel, F1, six topics, drift tests, on the command registry); more topics, tooltips from label plus hint, Show me revealing hidden controls and onboarding open (owner, 2026-10-18: "we need contextual help from v1 onwards, and an
onboarding process later"). Contextual help is part of the first version; onboarding
comes after. Needs WP4, WP5 (the command registry).

**Contextual help, v1.** Help that knows where you are: the focused panel, the
selected clip or track, the current mode. (1) A help key (`F1` or `?`, remappable)
opens a help panel for the focused thing; (2) every control and command has a
one-line hint (the registry's `hintKey`) and a longer help text, both translated
(English and Finnish) and kept as data files, not in code; (3) the menu and the
status line show hints and shortcuts (WP5); (4) empty states say what to do next
(already in the design); (5) a searchable help index reachable from the Help menu and
the palette; (6) help text can link to the matching setting or command and run it;
(7) the same registry feeds the cheat sheet, so help never drifts from the keys.

**Onboarding, later.** A first-run welcome with a sample project, a short guided tour
that does real edits and can be skipped or replayed, progressive tips tied to the
user's first use of each feature (shown once), and a checklist of the core loop
(import, listen, cut, undo, export). Design and content come after v1.

---

## Rules that come from real Hindenburg complaints (apply everywhere)

1. **Space is always the timeline transport.** No other panel takes Space.
2. **In/out is used only by range commands.** Drag, drop, paste and import
   ignore it.
3. **No level surprises.** Anything that previews audio outside the mix plays
   loudness-matched, never louder than the programme.
4. **Copying a clip never copies more audio than it uses** (WP20).
5. **Lining up files that share no clock is the app's job** (WP16), not the
   editor's eyes and hands.

---

## Things an implementer is likely to get wrong

- Using seconds in the model. Frames only.
- Committing on every mouse-move. Use `coalesce` for drags that should undo as
  one step, or commit once on mouse-up.
- Taking `session.lock` or doing file I/O in the audio callback.
- Writing directly to the final file name. Write `.partial`, then rename.
- "Fixing" a failing test by changing what it checks.
- Copying a speechmix constant's value instead of importing the name.
- Skipping a test when a tool (ffmpeg) is missing. Let it fail; ffmpeg is a
  requirement (`brew install ffmpeg`, `winget install ffmpeg`).
- Treating file names as identity. Use the SHA-256 media id.
- Adding a crossfade to a plain split. Crossfades are only for ripple joins of
  non-adjacent audio (`ops._crossfade`).

### WP49 — Loudness monitoring with a target per track

Status: open (owner request 2026-10-18). Needs WP22 (roles), WP4 (editor UI),
the density work.

Owner: "in the best possible version, the tracks would know what their target
LUFS level is, and they would display that as well. So you could eyeball the
levels." And: since speechmix mixes offline and automatically, live VU meters
are not very useful, but some visual monitoring still is.

So this is **monitoring from analysis, not live metering**: nothing new runs in
the audio callback.

- **Data:** short-term loudness (3 s windows, 1 s hop) per track and for the
  whole mix, computed by the analysis step (like `analysis.track_levels`),
  cached by content, recomputed in the background after an edit or a change
  of the mix. Plus the programme's integrated LUFS and true peak.
- **Target:** `Track.target_lufs` (float or None) in edit state, set in the
  inspector; role defaults: speech −19, music −23 (under speech), narration −19.
  Format addition: `min_reader` rule as for any new optional field. The same
  number is what "match loudness" aims at.
- **UI:** a thin loudness curve on each track lane against a line at the target;
  stretches beyond ±3 LU of the target are tinted (inside ±2 quiet). Active
  clips under the cursor are highlighted. The playhead reads the same curve
  (a number beside the cursor), and the transport bar shows the programme's
  integrated LUFS and true peak. Colours and animation from the visual grammar.
- **Tests first:** windowed loudness of a known signal, cache key follows the
  content, target round trips through save and undo, role defaults, tick and
  tint maths (pure JS).

---
