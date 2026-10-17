# Handoff: next tasks (updated 17.10.2026 05.11 Helsinki)

For any agent, from any vendor, picking up work on kuulas. Read `AGENTS.md`
(`CLAUDE.md` and `GEMINI.md` point to the same rules), then the ground
rules at the top of `docs/PLAN.md`, then your task's work package (WP) in
`docs/PLAN.md` and any format details in `docs/FORMAT.md`. The older handoff
`2026-10-16-model-handoff.md` describes how the first batch was integrated.

## State of the repo

- **main:** version 26.10.17.2: 521 pytest + 25 node tests pass, ruff and
  Biome are clean, and every test file also passes **on its own**. The repo
  has one branch besides main (`wp4-ui-shell`, the draft) and no other
  worktrees; the primary checkout is on `main` and clean.
- **Done and merged:** WP0, WP1, WP2 (engine; the owner's listening test is
  still pending), WP3 (HTTP API, `kuulas open`), WP9 (jobs, local
  transcription), WP11 (export mix, selection, tracks, MP3), WP13 (Hindenburg
  import), WP14, WP24.1, WP29, WP30, WP33a, WP33b, WP34, WP36, WP37, WP39,
  WP41, and the core of WP25 (music report: builder, CSV, HTML, tags read at
  import, English and Finnish; follow-ups below).
- **Not finished, and nobody is working on it:** WP4 (UI shell and timeline).
  An unreviewed draft is one commit (`4b85609`) on branch `wp4-ui-shell`,
  with its own plan in `docs/plans/2026-10-16-wp4-ui-shell.md` on that branch
  (tasks 1–4 started; task 5 and the acceptance checks remain). Review the
  draft against `docs/PLAN.md` WP4 before extending it. **Until WP4 merges, do
  not edit `ui/` or `server.py` on other branches;** everything else in the
  UI waits for it.
- First playable build (milestone M1, `docs/PLAN.md` Triage): WP4, then WP5
  keyboard, WP19a editing in sync, WP35 remembered settings. Recording is not
  in M1. Series features come last.

## First steps

1. In `/Users/dst/Documents/koodi/kuulas`, `git status` should be clean and
   `git branch --show-current` should say `main`. Do your work in worktrees,
   not in this checkout.
2. WP4 only: the draft branch can't be checked out twice, so use
   `git worktree add /private/tmp/kuulas-wp4 wp4-ui-shell`.
3. `uv sync` (needs `../podcast` next to the repo), then `uv run pytest -q`;
   it should report 480 passed.

## Rules (the short version; the ground rules are binding)

1. **One task, one worktree, one branch.** `git worktree add
   /private/tmp/kuulas-<wp> -b <wp>-<slug> main`. If `../podcast` does not
   resolve from the worktree, symlink it (`ln -s
   /Users/dst/Documents/koodi/podcast /private/tmp/podcast`) and never commit
   a change to `pyproject.toml` sources. **Never leave work uncommitted in the
   primary checkout.** If you stop, commit on your branch and say where it is
   (branch, worktree path, what is unfinished).
2. **Red-green TDD:** write the WP's tests first and watch them fail for the
   right reason. Never weaken a test or a lint rule.
3. **Clean before you commit:** `uv run pytest -q`, `uv run ruff check .`, and
   for UI `node --test ui/tests/` and `npx --yes @biomejs/biome@2.2.4 check ui/`.
4. **Every user-facing string** is a key in `src/kuulas/locales/en.json` and
   `fi.json` (natural Finnish), read through `kuulas.messages.t()` (Python) or
   `ui/i18n.js` (UI). The scan tests fail on literal text.
5. **Do not bump the version, and do not edit `CHANGELOG.md`, `ROADMAP.md` or
   the Status lines in `docs/PLAN.md`.** The integrator does that when
   merging, so parallel branches never conflict on them. Put a suggested
   changelog text (2–3 lines, for the person shipping) in your report.
6. **Small and additive in the hot files:** `session.py`, `history.py`,
   `model.py`, `ops.py`, `server.py` and the two locale files are touched by
   almost every task. Add; don't restructure. Locale conflicts are resolved by
   taking the union of keys.
7. **Fail soft, snappy, cached by content** (ground rules 13–15). Anything that
   reads files or devices gets fault-injection tests.
8. **Commit locally only, never push.** A commit made by a model says which
   model made it: end the message with the attribution lines your tool or the
   owner gives you (a Claude session gets a `Co-Authored-By:` line and a
   session link from its harness). This repo has no remote, so there are no
   pull requests: branch per task, merge locally.
9. **Report briefly:** branch and commit, test counts before and after,
   suggested changelog text, what you could not verify, and any decision the
   plan did not cover.
10. **Tests pass alone and in any order.** `tests/conftest.py` starts every
    test in English and restores the language, because the default language
    follows the machine (Finnish on the owner's Mac). Don't depend on global
    state another test sets, and run each new test file on its own before you
    commit.

## If you are not a Claude session

Everything you need is a shell with `git`, `uv` and `node`; no Claude-specific
tool, skill or subagent is required.

- **Commands:** `uv sync`, `uv run pytest -q`, `uv run ruff check .`,
  `node --test ui/tests/`, `npx --yes @biomejs/biome@2.2.4 check ui/`.
- **Languages:** code, tests and commits in English; every user-facing string
  in English and Finnish. The owner is in Helsinki: show absolute times in
  Helsinki time with the zone named.
- **Never put a secret on a command line or in chat.**
- **Say what you could not verify.** You cannot play audio through a real
  device or open a browser unless your environment can; the plan marks the
  hardware test as the owner's. Do not claim it passed.
- **Do not copy code from speechmix or nhsx** (the podcast repo); import them.
- **Long reasoning is no substitute for the tests:** the plan lists the tests
  each work package needs. Write those first.

## Task board

Model = the capability tier that should build it. The names are Claude models
used as tier labels: **Haiku = small and mechanical** (the spec and tests
leave nothing to decide), **Sonnet = the normal tier** (most work, including
UI), **Opus = the strongest tier** (real-time audio, schema changes,
judgement calls; review closely). Models of similar tiers from any vendor can
take these tasks. Size: S about a day, M a few days, L a week.

### A. Start now: backend only, safe next to WP4

| Task | Model | Size | Touches | Notes |
|---|---|---|---|---|
| WP19i onset detection (backend) | Sonnet | M | new `onsets.py`, `media` caches | cached per media by content hash; word mode waits for WP7 |
| WP10 voice chain variants | Sonnet | M | new module, `media`, `session` | offline per source file; **do not build the plug-in audition** (requested from speechmix, see section E) |
| WP20 paste without bloat | Sonnet | M | `media`, `session` | excerpts keep recorded time; the picker UI waits for WP4 |
| WP26 fast listening, JKL, scrubbing (engine side) | **Opus** | L | `engine.py` | time-stretch with pitch kept, scrub tactics in the WP; the keys wait for WP5 |
| WP23a FX layers, real-time and analyse-then-live tiers | **Opus** | L | `engine.py`, `model` | dxRevive is offline-only by decision; read the WP23 text on where heavy restoration goes |
| WP18 cut candidates (model, anchoring, preview) | **Opus** | M | `model`, `ops`, `session` | markers anchored to the recording clock; WP21, WP31, WP32 reuse this |
| WP40 long history stays fast | Sonnet | M | `history` | budgets and the incremental backups; thinning only as a safety valve |

### B. Backend halves that touch the hot files: run one at a time, or give them to one agent

| Task | Model | Size | Notes |
|---|---|---|---|
| WP19a edit target rule | Sonnet | M | `Session.edit_target`, partners found by recording time; free-from-sync and drift states; the UI highlighting waits for WP4 |
| WP22 track tags and ducking | Sonnet | S | `speech` / `speech-mix` / `music`, `analysis.duck_music` through `nhsx.musicbed`; header toggle waits for WP4 |
| WP8 history: session markers, stateful undo context | Sonnet | M | `History.commit(context=...)`; the panel waits for WP4 |
| WP21 several edits | **Opus** | L | switching and "new edit from range" first; `offer_cuts` waits for WP18 |

### C. Waits for WP4 (and mostly WP5) to merge

WP5 keymap and palette (Sonnet, first) → WP19a UI, WP35 remembered settings →
then the UI parts of WP22, WP8, WP19i, WP26, WP20's picker, plus WP6 mouse
editing, WP7 transcript panel, WP28 focus mode, WP19f spot (Haiku),
WP19h regions and chapters (Haiku, after WP18), WP19g skimming, WP24.2 A/B,
WP43 narration placeholders, WP31, WP32, WP19b-e.

### D. Simple pool: small, well-specified, good for Haiku or small Sonnet runs

Done and merged (agy, reviewed by the coordinator): WP25 follow-ups, delete
commands for people and interviews, the test-environment fix, the
decoded-chunk cache under the memory budget, rebuild of damaged media, the
manual transcription smoke test, and the default-output-switch findings
(recorded under WP2). Still open:

1. **Onset detection, backend only (WP19i).** In progress (agy, task T8).
2. **WP40 first step:** a generated 5,000-step history, tests for the open,
   undo and history-page budgets, and a paged `History.nodes_page`. Ask before
   touching the schema.
3. **Clearing the engine's damaged mark after a rebuild.** Needs a decision
   about `engine.py`'s narrow surface first: ask the coordinator.
4. **Lower `IDLE_CLOSE_S` to about 5 s** so a changed default output is picked
   up at the next play (see the WP2 finding); small, but the owner should say
   whether the slower first play after idle is acceptable.

### E. Do not start: needs a decision or another repo first

- **Colab transcription** needs a plain-audio mode in `colab-transcribe` (the
  podcast repo); not built, and a change there needs the owner's go-ahead.
- **Voice presets and the plug-in audition function** were sent to the
  podcast session as a request for speechmix; WP10 and WP23 must use them
  when they exist, not rebuild them.
- **Hindenburg export** (R35's other half) has no WP yet; write the plan
  paragraph first.
- **Recording (WP12), align by sound (WP16), settings and rate change
  (WP27), series (WP38, WP42), desktop wrapper (WP15)** are later phases.

## Merging (for whoever integrates)

Merge one branch at a time with `git merge --no-ff`, running pytest and ruff
after each; resolve locale conflicts by union and `session.py` conflicts by
keeping both additions; stop and report on a real design clash. Then one docs
commit (check afterwards that every file you meant to change is in
`git show --stat`; a half-applied docs script once left a commit that only
bumped the version): version, `CHANGELOG.md`, the Status lines in `docs/PLAN.md`,
`ROADMAP.md`, and this file. Remove merged worktrees and branches.
Keep at most four agents running at once.

## Open for the owner

- Music report times round up to whole seconds (decided 2026-10-17). The
  Teosto and Gramex file layout is still unknown.
- The engine listening test: `cd ~/Documents/koodi/kuulas && uv run pytest -q
  tests/hardware -s` (volume down; it plays one second of a quiet tone).
- The format decisions were built with the recommended answers (package
  folder, keep all history, no OpenTimelineIO yet, a second machine opens
  read-only); say if any should change.
- Whether "send for review" should carry only used audio by default (WP32).
- Roadmap page: the milestone grouping of tasks is not done yet.
- Which model takes WP4; it gates all UI work, so it deserves a model that
  can review a draft critically and finish it.
