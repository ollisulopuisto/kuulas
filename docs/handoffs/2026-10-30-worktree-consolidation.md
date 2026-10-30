# Worktree consolidation — 2026-10-30

Audited the registered worktrees and local branches against the locally known
`origin/main` (`37902a8`). Consolidated these changes for the next main build:

- Recording loudness reader failures are logged once per failing input and
  reported again after recovery (`095fa53` patch, integrated as `6edd56a`).
- Music-level offsets now support up to +1 dB, with linked numeric and slider
  controls and updated English/Finnish copy (`8d0dba8`). Current release
  version metadata was retained.
- Adjacent transcript words can be corrected together (`df4ad8f`).
- Test cases share one private user-state root; CI records slow-test durations
  and uploads the pytest report, preserving the current path filters and
  platform-specific test selection (`7506997`).
- Text > Transcribe groups actions by local/Colab provider and track/all
  recordings; Colab all-recordings goes through the existing upload consent
  (`cc2d38b`).

Other branch outcomes were already represented by newer main code: muted-copy
behavior and the CodeQL fixes; both parents of the old PR #25 merge; and the
older Orukeet and WP26 grain implementations. The useful WP26 integration cases
for crossing a skipped region and ending a short project were carried into the
current grain-engine tests. Stale roadmap text was not reapplied.
Uncommitted `uv.lock` edits only bumped old Kuulas versions, or repeated the
already-locked `silencelearn` dependency. The duplicate recording-meter draft
matches the diagnostics change above.

No local tests were run, per the owner's instruction. GitHub CI is the
verification path for the consolidated commits.
