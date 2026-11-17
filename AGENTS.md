# kuulas: instructions for any coding agent

kuulas is a local multitrack spoken-word editor (Python 3.13 engine, browser UI
in `ui/`). It imports `speechmix` and `nhsx` from the podcast repo at
`../podcast`; never copy that code.

Start here:

1. `docs/handoffs/2026-10-16-next-tasks.md`: what to work on next and how.
2. `docs/PLAN.md`: the ground rules at the top (binding) and the work
   package you are doing. `ROADMAP.md` says what kuulas must do.
3. `docs/FORMAT.md` for anything stored in a project.

Non-negotiable, in short:

- Red-green TDD: write the work package's tests first, see them fail, then
  implement. Never weaken a test or a lint rule.
- Before committing: `uv run pytest -q`, `uv run ruff check .`; for UI
  `node --test ui/tests/` and `npx --yes @biomejs/biome@2.2.4 check ui/`.
- Every user-facing string is a key in `src/kuulas/locales/en.json` and
  `fi.json` (natural Finnish).
- One task, one git worktree and branch. Work lands as a pull request;
  the owner reviews and merges, agents never push to main. Do not
  bump the version or edit `CHANGELOG.md`, `ROADMAP.md` or PLAN status lines
  unless you are the integrator.
- This repo is on GitHub (`ollisulopuisto/kuulas`) and uses pull requests,
  like the owner's other repos (for example vikasietotila's `GEMINI.md`).

## Coordinator channel (agents that take tasks from the coordinator)

Each such agent has a pair of files in
`/Users/dst/Documents/koodi/kuulas/.agents/`, named after it: `agy.md` and
`agy-reply.md` for agy, `opencode.md` and `opencode-reply.md` for opencode.
Tasks, rules and review verdicts arrive in `<name>.md`; you answer only in
`<name>-reply.md` (append-only). Each file has exactly one writer, and you
use only your own pair. The folder is not in git, so use the absolute path from
any worktree. The protocol is at the top of your `<name>.md`: re-read it before
every task, claim a task before starting, and report when it is ready for
review.

## Repo facts (verified 2026-11-17)

Checks (mirroring `.github/workflows/ci.yml`):

- Python 3.13: `uv sync`, then `uv run pytest -q` and `uv run ruff check .`
- UI: `node --test ui/tests/*.test.js` and `npx --yes @biomejs/biome@2.2.4 check ui/` (Node 24)
- Audio tests need ffmpeg plus PortAudio/libsndfile. Ubuntu: `sudo apt-get install -y ffmpeg libportaudio2 libsndfile1`; macOS: `brew install ffmpeg`.
- The engine imports `speechmix` and `nhsx` as path dependencies from a sibling checkout of `ollisulopuisto/podcast` at `../podcast`; without it `uv sync` and the tests fail.

CI quirks:

- CI is change-scoped (dorny/paths-filter in `.github/workflows/ci.yml`); documentation-only PRs skip the Python/UI suites. Full suites run on workflow_dispatch and the weekly schedule.
- The two macOS pytest shards are the merge gate and start immediately; the Ubuntu shards run staggered behind them, so the Mac result lands first. Windows is off: it is red on main and was disabled by the owner on 2026-10-26 (comment in ci.yml).

Known flaky tests (timing-dependent; fail under load, pass alone):

- `tests/test_recorder_capture.py::test_writer_stall_becomes_silence_not_a_shift` - recorder audio timing; failed 2026-11-17 on an unrelated diff, green on rerun.
- `tests/test_background_transcribe.py::test_a_finished_transcript_is_added_automatically_with_a_notice` and the recorder SIGKILL test `test_sigkill_of_the_whole_recorder_leaves_readable_files` (recorded in ROADMAP.md, 2026-10-20).
- The Colab cancel tests `test_colab_session.py::test_cancel_stops_the_tool_and_stores_nothing` and `test_colab_transcribe.py::test_cancel_stops_the_process_and_removes_the_folder`, and the `test_engine_stretch` block-cost test (recorded in ROADMAP.md).
- If one of these fails on an unrelated diff, confirm main passes it and say so in the PR instead of "fixing" it.

Merge gate: a PR merges only when Devin review shows no open findings on the current head and the required CI checks are green (owner's standing rule). If Devin has not reviewed the current head, wait for it instead of merging on CI alone.

Loop guard: if the same check fails twice with the same error, stop. Report the command, the error and what you tried instead of retrying a third time or patching blind.
