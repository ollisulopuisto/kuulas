# CI and urgent builds

## Normal pull requests

Pull requests that change code run the full lint and test suite on macOS and
Linux. A docs-only change skips that 2,850-minute Python test workload. Merging
does not run the same two-platform suite again on `main`; this avoids paying
for an identical second run after the required pull request checks passed.

The Linux desktop smoke check runs only when the desktop wrapper, its tests,
or Python dependency configuration changes. Run it manually from Actions when
you need to recheck that boundary without changing those files. The complete
CI workflow also has a manual `workflow_dispatch` trigger for a full two-OS
recheck.

## Hotfix build without waiting for full CI

The `dmg` workflow is deliberately independent of CI. In Actions, select
**dmg → Run workflow** and choose the hotfix branch. It builds the app and runs
the packaging self-test, then uploads a downloadable artifact for 30 days. A
`v*` tag triggers the same build and publishes the DMG and checksum to a GitHub
Release. This path allows an urgent fix to be packaged while the full test
matrix is still running; review the change and the DMG self-test result before
tagging a release.

The manual DMG build does not run the full Python/UI suites, and an artifact
from a branch is not a GitHub Release. Keep those checks and release steps
explicit when urgency requires bypassing the usual PR gate.

## Rebuild a committed release locally

On an Apple-silicon Mac with full Xcode selected, `uv`, `git`, and network
access, use the release wrapper from a Kuulas checkout:

```sh
scripts/build_release_dmg.sh --ref v26.10.30.2 --out ~/Desktop/kuulas-dmg
```

The wrapper builds the exact Kuulas tag and the Podcast commit pinned by the DMG
workflow (`5a179e6f16024a0e1aa6fa9d01a0edcb09cdf2fc`). It fetches `origin/main`
if that Podcast commit is missing from the local object database, then creates
temporary detached worktrees and removes them when the build finishes. The
source checkouts are left untouched. Use `--podcast-repo PATH` if the sibling
`../podcast` checkout is elsewhere, or `--podcast-commit SHA` to reproduce a
different workflow pin. `scripts/build_release_dmg.sh --help` lists all options.

The lower-level `scripts/build_dmg.sh` remains available for CI and for callers
that already manage a clean Kuulas checkout and `PODCAST_SRC` themselves.
