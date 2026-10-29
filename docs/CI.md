# CI and urgent builds

## Normal pull requests

Every pull request runs the full lint and test suite on macOS and Linux. Merging
does not run that same two-platform suite again on `main`; this avoids paying
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
