# Kuulas benchmark handoff, 29 October 2026

Status checked at 09:27 Europe/Helsinki. Owner: Instinct benchmark-maintenance lane. Scope: test measurement correctness and diagnostics only; implementation is landed, with release verification and the latency decision still open. This dated handoff uses the established tracked handoff convention, not a new claim ledger.

## Landed work

- PR78: https://github.com/ollisulopuisto/kuulas/pull/78 . Merged 08:58:57 Helsinki, merge e9434eb9186671c7833ea2f2a714ab4bc829b5cd. Cut-preview lock benchmark now snapshots durations before Session.close, so shutdown/database flush is not counted as preview work. Delayed-close regression exercises the old failure. The 5ms threshold and production code are unchanged.
- PR79: https://github.com/ollisulopuisto/kuulas/pull/79 . Merged 08:57:53 Helsinki, merge 59fe1adabee25269b9505a7685d0f10b161a0bd6. Adds redo wall/CPU/SQL/commit diagnostics, bounded SQL tests at 50/5000 steps, FULL durability/reopen checks and delayed-commit diagnostics regression. The 50ms end-to-end gate remains unchanged. This is not a proven fix for the previous 77.4ms CI sample.
- Current main e9434eb9 contains both changes, verified in source and merge history, not inferred from closed PR state.

## Verification and open limits

- Local cut-preview/source-map tests: 17 passed, including delayed-close red/green reproduction and three additional repeated benchmark pairs.
- Local history/page/growth/scale tests: 42 passed. Expanded history/undo-context/restore-cuts/take-restore/cut-preview/source-map verification: 82 passed on the diagnostics branch.
- Ruff and diff checks passed. Existing Starlette/httpx deprecation warning remains.
- Adjacent redo uses 13 SQL statements at both 50 and 5000 steps in local profiling. SQLite query plan uses covering index nodes_by_parent_id(edit,parent). These observations do not identify the cause of the failing CI sample.
- Actual merged-main CI/release follow-through belongs to the existing release coordinator. No new release or native runtime success is claimed here.
- Owner has not approved changing the 50ms wall-time requirement to CPU time. Do not silently relax it, retry until green, disable FULL durability or treat diagnostics as release clearance.

## Ownership boundaries

Codex owns unfinished incremental backups WP40, per-range history WP80/restore and recording-meter diagnostics in separate local worktrees. The supplied takeover screenshot reports drafts based on 10f84fb5, no pushes/releases, 36 tests passed, and a still-unreproduced blank meter. Those are external-worker reports, not independent verification. Do not duplicate these implementations. Production history.py, backup, range-history and LUFS code were not changed in this benchmark lane.

## Coordination route gap

AGENTS.md describes untracked, per-writer claim/reply files under the Mac checkout's .agents directory. No assigned pair or accessible copy is available here. The tracked docs/handoffs directory contains dated narrative handoffs; no tracked BOARD/CODEX/TASKS/TODO ledger was found. This tracked dated handoff records only this lane under the owner's 29 October coordination instruction. It does not replace or edit Codex's single-writer record. No owner bug statuses or roadmap statuses were changed.


## Review and rollback

Changes were isolated on fix/cut-preview-benchmark-scope (78) and fix/history-scale-diagnostics (79). This documentation branch changes only this file. Revert this documentation commit independently if its placement becomes obsolete. If a benchmark change needs reverting, review the named PR's diff and use a separate human-reviewed revert; do not revert unrelated feature work or relax the latency budget. No automatic rollback or merge is authorized by this handoff.
