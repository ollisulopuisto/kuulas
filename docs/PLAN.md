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
the way, in order: WP33a (done), WP29 (done), WP30 (done), WP1, WP2, WP3, WP33b,
WP4, WP5, WP19a (editing in sync), WP11 (WP11 can run in parallel with WP4). Everything else in phase 1 follows
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
| 7 | WP2 playback engine | M | glitch-free real-time callback, prefetch | **Opus 5.5** |
| 8 | WP3 HTTP API + CLI | M | none | Sonnet 5.5 |

### Phase 1 — MVP: an editor you can actually use

Exit test: import a 2-mic interview, transcribe it, listen through at 1.5×,
cut by text and by keyboard, Tab through transients, automix with a real-time
plugin on a voice, undo anything, export a mastered file.

| Order | WP | Size | Hard part | Model |
|---|---|---|---|---|
| 9 | **★ WP33b i18n in the UI (R39)** | M | Intl formatting, key names, literal-text check | Sonnet 5.5 |
| 10 | WP4 UI shell + timeline | L | canvas drawing, zoom, hit-testing | Sonnet 5.5 |
| 11 | **★ WP5 keymap + palette (R10)** | M | many bindings, collision test | Sonnet 5.5 |
| 12 | **★ WP19a edit groups: what an edit touches (M1)** | M | target × time-shifting rule, partners by recording time | Sonnet 5.5 |
| 13 | **★ WP8 history panel + stateful undo (R29)** | M | ledger restore, context restore, change flash | Sonnet 5.5 |
| 14 | **★ WP22 track tags + ducking (R30)** | S | music-bed curve from nhsx | Sonnet 5.5 |
| 15 | **★ WP26 fast listening + JKL (R33)** | L | streaming time-stretch, JKL state machine | **Opus 5.5** |
| 16 | **★ WP19i tab to transient / word (R26i)** | M | onset detection; word mode waits for WP7 | Sonnet 5.5 |
| 17 | WP6 mouse editing | M | drag state machine | Sonnet 5.5 |
| 18 | WP9 jobs + local transcription | M | parallel faster-whisper | Sonnet 5.5 |
| 19 | WP7 transcript panel | M | selection → word indices | Sonnet 5.5 |
| 20 | **★ WP23a FX layers: real-time tier + analyse-then-live tier (R30)** | L | real-time plugins in the callback, latency compensation, CPU meter | **Opus 5.5** |
| 21 | WP11 export + mastering | M | parallel ordered render | Sonnet 5.5 |

### Phase 2 — The editing loop (what makes it better than Hindenburg)

| Order | WP | Size | Hard part | Model |
|---|---|---|---|---|
| 22 | WP28 focus mode | M | lane layout, speaker focus, solo restore | Sonnet 5.5 |
| 23 | WP18 cut candidates | M | recording-clock anchoring (later WPs reuse it) | **Opus 5.5** |
| 24 | WP19f spot | S | parsing | Haiku 5.5 |
| 25 | WP24.2 A/B | M | edit A/B position mapping, level match | Sonnet 5.5 |
| 26 | WP21 several edits (versions) | L | history schema migration, offer_cuts | **Opus 5.5** |
| 27 | WP31 changes view + checkpoints | M | recording-range diff | Sonnet 5.5 |
| 28 | WP32 review round trip: suggest mode, hand-off, merge | L | diverged copies become suggestions | **Opus 5.5** |
| 29 | WP20 paste without bloat | M | excerpt media keeping recorded time | Sonnet 5.5 |
| 30 | WP19c roles, stems, match loudness | M | stems sum test | Sonnet 5.5 |
| 31 | WP19d remappable keys + macros | M | macro = one undo step | Sonnet 5.5 |
| 32 | WP19b connected clips | M | reflow after every edit | Sonnet 5.5 |
| 33 | WP19h regions + batch export, chapters | S | none | Haiku 5.5 |
| 34 | WP19g skimming | S | grain throttling | Sonnet 5.5 |
| 35 | WP19e alternative takes | L | ripple on take length change | Sonnet 5.5 |

### Phase 3 — Pipeline depth

| Order | WP | Size | Hard part | Model |
|---|---|---|---|---|
| 36 | WP14 parallel analysis (done) | S | none | Haiku 5.5 |
| 37 | WP10 voice chain variants | M | variants, chain settings | Sonnet 5.5 |
| 38 | WP25 music report | S | heard-duration rules | Haiku 5.5 |
| 39 | WP13 Hindenburg import | M | `.nhsx` word clock | Sonnet 5.5 |
| 40 | WP23b FX layers: render tier, export waits, freeze on overload | L | background render, overload policy | **Opus 5.5** |

### Phase 4 — Recording and alignment

| Order | WP | Size | Hard part | Model |
|---|---|---|---|---|
| 41 | WP12 recording, foolproof mode, live logging | L | hardware, crash recovery, sleep prevention | **Opus 5.5** |
| 42 | WP17 clip bin | M | Space and in/out rules | Sonnet 5.5 |
| 43 | WP16 align by sound | **XL** | drift and dropout detection | **Opus 5.5** |

### Phase 5 — Late

| Order | WP | Size | Hard part | Model |
|---|---|---|---|---|
| 44 | WP27 settings + rate change | L | converts every position kind; do it when the model has stopped growing | **Opus 5.5** |
| 45 | WP15 desktop wrapper | M | packaging | Sonnet 5.5 |

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

Status: open. Needs WP0.

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

Status: open. Needs WP1.

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

Hardware smoke test `tests/hardware/test_play.py`: plays 1 s of a sine through
the default device; run by hand on Mac and Windows.

---

### WP3 — HTTP API and CLI

Status: open. Needs WP1, WP2.

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

Status: open. Needs WP3.

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

Tests: UI logic that is not drawing goes into pure functions in
`format.js` and `store.js`; test them with `node --test ui/tests/` (Node's
built-in runner, no dependencies). At minimum: frame/time formatting, zoom
math (frame ↔ x), hit testing (x,y → clip id, edge, envelope point).

Acceptance: open a folder with two imported WAVs, see both lanes with
waveforms, play with Space, see the playhead move.

---

### WP5 — Keyboard: the Hindenburg keymap

Status: open. Needs WP4. This is the most important UI WP (R10).

New files `ui/keymap.js` (the table), `ui/commands.js` (one function per
command, each taking the store and returning nothing). `Mod` is Cmd on Mac and
Ctrl elsewhere (`navigator.platform` / `userAgentData`). Keys are matched on
`event.key` plus modifiers. When focus is in a text input, only Esc and
Mod-combinations act.

Every command is also in a command palette (Mod+K): a filterable list of
command names with their keys, so everything is discoverable without a mouse.

Source of the bindings: Hindenburg PRO's own list,
<https://hindenburg.com/academy/shortcuts/shortcuts-hindenburg-2-pro/>.

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

Status: open. Needs WP4.

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

Status: open. Needs WP1.

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

Status: open. Needs WP1.

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

Status: open. Needs WP1.

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

Status: open. Last.

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

Status: open. Needs WP1, WP4, WP5. High value: this is the user's core
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

Status: open. Each part is its own small WP (19a–19i), commit each separately.
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
- Mod+G toggles group editing for the session. When it is off, the toolbar
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
import (a job) and cached as `media/<id>.onsets.npy` (source frames):

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

Status: open. Needs WP1, WP4. Small; do it early (right after WP4).

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
  full source render starts. If speechmix measures that the parameter is a
  linear dry/wet mix, offer a continuous slider by blending one 100 % render
  with the original instead.
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

Status: 24.1 done in v26.10.16.2 (mixer rule and `ops.solo`; the coalesce
key waits for the Session in WP1, and the keys for WP5). 24.2 open. Part 1 needs only WP0, so do it right after WP0. Part 2 needs
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

Status: open. Needs WP1, WP11, WP22 (music tags), WP21 (per edit).

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

Status: open. Needs WP2, WP5.

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

Status: open. Needs WP8, WP18 (recording-clock anchoring), WP21. Sonnet 5.5.

Compare any two points: two history steps, a checkpoint, or two edits.

- **Checkpoints:** **Mod+Shift+K** names the current step ("sent to
  producer"). Checkpoints are ledger entries
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
speechmix translator, literals converted); WP33b open. **Split in two**, so no
WP writes untranslated text:
- **WP33a** (Python: catalogs, `messages.t`, API error shape, speechmix
  translator, converting today's literal messages in `ops`, `media`,
  `transcribe` and `analysis`). Needs WP0. Haiku 5.5. **Before WP29.**
- **WP33b** (UI: `ui/i18n.js`, `Intl` formatting, key names, the language
  setting, the UI literal-text check). Needs WP3 and WP33a. Sonnet 5.5.
  **Before WP4.**

English is the source language; Finnish is complete from day one.

Left over from WP33a, to do in WP33b: on macOS a Terminal session usually
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
