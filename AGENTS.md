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
- One task, one git worktree and branch. Commit locally, never push. Do not
  bump the version or edit `CHANGELOG.md`, `ROADMAP.md` or PLAN status lines
  unless you are the integrator.
- This repo has no remote and no pull requests, which differs from the
  owner's other repos (for example vikasietotila's `GEMINI.md`).
