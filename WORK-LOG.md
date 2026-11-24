# Work log

## 2026-11-21: Free-only security pilot

Review: Instinct, branch `agent/security-pilot-free`, isolated security-pilot worktree. Adds report-only, pinned scanners and weekly staggered public-hosted runs. See `docs/security-pilot.md` for coverage, output and limits. No app behavior/version change, fixes, releases, private CI, or merges.

Security pilot review follow-up: include merge-resolution patches, tolerate null RustSec advisory warnings, fix native Go scan tags, and conform to repository lint. Added two regressions (both failed against the old implementation). CodeQL pin resolves in hosted CI; no change based solely on an external 404 claim.

## 2026-11-24: CUDA experiment decoder compatibility

The experiment pins faster-whisper 1.2.1, which still passes metadata_errors to av.open. Bound its transcribe extra to av<19; the lock resolves 18.1.1. Only av changes package version. Python 3.13 locked base sync and four transcription tests pass; extra sync dry-run resolves. Full GPU/Colab installation and inference remain unrun here. No main merge or production dependency change.
