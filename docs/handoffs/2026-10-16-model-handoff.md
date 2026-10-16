# Model handoff — 2026-10-16

Read `CLAUDE.md`, then `docs/PLAN.md` (ground rules and Triage) and the
work package before changing code. Keep each task in its own worktree, use
test-first development, keep Ruff clean, add English and Finnish text for every
message key, and commit locally only. Do not push.

## Work completed in isolated worktrees

These are local commits in separate worktrees. They have **not** been merged
into `main`; review and integrate them before treating the roadmap or release
documentation as current. WP-specific docs are in their respective branches.

| WP | Commit | Worktree | Verification reported |
|---|---|---|---|
| WP11 — export | `4869824` | `.claude/worktrees/agent-a1170057bf5beefec` | 409 pytest passed; Ruff clean |
| WP37 — usage extractor | `2cecb73` | `/private/tmp/kuulas-wp37` | 413 pytest passed; Ruff clean |
| WP39 — portable projects | `9343406` | `/private/tmp/kuulas-wp39` | 417 pytest passed; Ruff clean |
| WP9 — background jobs and transcription | `e41f6aa` | `/private/tmp/kuulas-wp9` | 414 pytest passed; Ruff clean |
| WP13 — Hindenburg import | `7795489` | `/private/tmp/kuulas-wp13` | 412 pytest passed; Ruff clean |

The WP11 attempt is already in its worktree; inspect and reuse it rather than
recreating the work. The test counts above are from the task agents' reports.

## Current checkout and next work

- WP4 (L, UI shell and timeline) is intentionally left for a larger model.
  The main checkout contains an in-progress WP4 draft, including
  `docs/plans/2026-10-16-wp4-ui-shell.md`. Preserve and review that work; its
  plan reports tasks 1–4 started, with task 5 and acceptance checks remaining.
- After WP4, continue the first playable build in order: WP5 keyboard, WP19a
  editing in sync, then WP35 remembered settings.
- Other small UI tasks identified as unblocked after WP4: WP19f, WP19h, WP19g,
  WP28, WP43, and WP24.2.
- The roadmap milestone grouping is still outstanding.
- The owner's engine listening test is still outstanding. Turn the volume
  down first, then run `cd ~/Documents/koodi/kuulas && uv run pytest -q tests/hardware -s`.

## Integration notes

The isolated task branches may have different bases. Review their ancestry and
diffs before merging, then reconcile any conflicts. At integration, update the
version, `CHANGELOG.md`, `ROADMAP.md`, and `docs/PLAN.md` status lines together
so those files describe only work that has actually landed. Parallel task
agents should leave those release and status records alone.

No hardware listening test, roadmap milestone regrouping, or merge of these
worktree commits is recorded as complete here.
