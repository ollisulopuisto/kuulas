# Work log

## 2026-11-21: WP25 report audibility

Branch `fix/music-report-audibility`. Initial patch had no UI or playback change. Seven initial
failing regressions reproduced music-report disagreement with actual mixer
routing. An immutable report snapshot now applies solo-overrides-mute and
muted-bus precedence to both use extraction and speech classification.
Independent review found no production defects and requested broader matrices;
those now cover plain mute, two solos, missing/None buses, and multiple speech
lanes, with actual mixer-output comparisons. Focused report/usage: 44 passed.
All 12 full-suite shards ran: 5,812 passed, one platform skip, one failure in
packaged selftest because the local system has no PortAudio library. The initial
unsharded attempt timed out. Accessible-only PATH fixed an unrelated missing-
command PermissionError in this environment. No shallow skip or source workaround
was added. Ruff check and diff check pass. Mac runtime and DMG not run.
Reports follow the master mix, including persisted solo state, not stem exports.

Owner follow-up: show a one-line notice when saved solo excludes otherwise
available music in the report span. The approved note sits below the scope,
above the summary. It stays visible for an empty result and travels in the JSON
response, CSV/HTML downloads and copied TSV, from the same immutable snapshot.
Already muted music and music outside the selected span do not trigger it.
Existing row-only session callers remain compatible. English and Finnish added.
Failing-first warning regressions: initial fixture setup failure corrected, then
four meaningful failures confirmed with the warning disabled; all pass with it.
Copy regression also failed before implementation. Focused backend: 184 pass.
UI suite: 4,001 pass. No new network behavior. Native Mac runtime not tested here.
Actual Chromium dialog smoke (offline fixture): empty and populated notices,
copy including notice, reopening clears stale notice. Pixel inspection confirmed
warning is readable beneath scope and above summary with the real token/style
sheets. Initial smoke harness lacked tokens and plural translation support;
corrected harness, no production workaround. Screenshots retained for review.
Ruff passes; Biome has no errors (24 existing warnings).

Devin follow-up: reproduced the selection-in-a-merged-gap warning and displaced
CSV/TSV headings, then fixed both. Warning detection uses unmerged usage ranges.
CSV/TSV keep the established header first and put one rectangular warning-only
record last, in the metadata column; its order and all music fields stay blank.
App-only notes recovered: reused transcript.silent_tracks instead of duplicating
master routing; empty reasons now use the existing export routing helper and
name solo/bus silence rather than falsely blaming gates; removed the unsupported
changelog subheading rather than expanding the Markdown renderer.
Focused backend: 186 pass. Full UI: 4,003 pass; Ruff clean, Biome no errors.
Actual styled Chromium smoke repeated for empty/populated reports and copy/reset.
Mac shard c00e438 failed the pre-existing engine-stretch p99 timing assertion
(7.23 ms vs 3.44 ms); report tests and all other jobs passed. No test was weakened,
no old-head rerun requested; this fix push will get fresh required CI.

## 2026-11-21: Free-only security pilot

Review: Instinct, branch `agent/security-pilot-free`, isolated security-pilot worktree. Adds report-only, pinned scanners and weekly staggered public-hosted runs. See `docs/security-pilot.md` for coverage, output and limits. No app behavior/version change, fixes, releases, private CI, or merges.

Security pilot review follow-up: include merge-resolution patches, tolerate null RustSec advisory warnings, fix native Go scan tags, and conform to repository lint. Added two regressions (both failed against the old implementation). CodeQL pin resolves in hosted CI; no change based solely on an external 404 claim.

Further Devin follow-up: copied TSV did not include CSV's Metadata column, so a
warning in its final cell was under Use. Added a failing header-aware regression.
When warnings exist, TSV now appends a localized Metadata column, pads music rows
with empty cells there and leaves the warning row's Use cell empty. No-warning
TSV remains unchanged. Incoming main conflict was only independent WORK-LOG.md
additions; kept both histories. Security-pilot files from main were not modified.

## Security advisory fixes, 2026-11-21

Branch: `agent/security-advisory-fixes`. Owner: Instinct. Status: Review pending.

Patch the locked opentelemetry-api dependency without changing the editor. This removes CVE-2026-126360. The Torch advisories remain because the tested resolver path to Torch 2.13 changes Linux CUDA 12 to CUDA 13, which needs an owner decision and GPU testing. No merge or release is requested.


<details><summary>Verification and limits</summary>

- uv lock updates only opentelemetry-api 1.45.1 to 1.45.2.
- Frozen all-extras/all-groups registry audit: three records before, two Torch records after. Local/project dependencies are outside the PyPI audit.
- uv sync and Ruff pass. The full pytest run exceeded 95 seconds with failures, not a pass. Its first failure is test_automix.py::test_missing_command_is_one_clear_error: PermissionError in this environment. The same test fails on unchanged main in the same environment.
- Torch 2.13.0 + TorchAudio 2.11.1 resolves and audits with zero records, but introduces a CUDA major runtime change. It is excluded. TorchAudio 2.11 supports Torch 2.11 and later: https://docs.pytorch.org/audio/stable/installation.html
- Optional transcription, real GPU, native Mac and hardware audio checks were not run. No CI or scanner-pilot files changed.
- Own review: lock diff and hashes checked, only the intended patch retained. Devin review requested separately.

</details>

## CI gate follow-up: deterministic read-only ingest test

Ubuntu shard 2 failed twice because its 50 ms watcher can legitimately ingest the test result before the test sets read-only. Stop and join that session's watcher before manually producing/polling its result. Test-only change, no runtime behavior change. Run the complete background-transcription module and lint before CI.

Main sync: retained newer dependency-security update and its transcription
fixture fix; resolved only work-log text. Fresh current-head checks required.

Devin latest-head follow-up: the empty-selection explanation must not blame a
muted bus or solo when that music lies outside the selected span. Added failing
regression, keep selection explanation neutral (whole-edit routing explanations
unchanged). CSV's warning-only record is intentionally not a music use: consumers
count numbered records, not every post-header record. Documented this distinction.
Full UI suite after selection-reason fix: 4,005 passed. Ruff passes; Biome
has no errors, 24 existing warnings. Styled dialog smoke repeated successfully.

## 2026-11-25: A2 Mac system shortcut defaults

Branch fix/mac-system-shortcuts, based on current fork main03fb1589. Inspected
main, open/recent PRs and all branches for duplicate shortcut work, none found.
Approved A2: history.part_versions moves from Option-Command-H to
Shift-Command-H; clip.mute drops only its Option-Command-M Mac alias and keeps M.
Shared DEFAULT_KEYMAP continues to drive dispatch, hints and palette. Other
platforms and explicit saved overrides stay unchanged. Version26.11.25.1.
Own adversarial review RAN: traced resolveKeymap override merge, exact modifier
matching, context collisions, command hints and native menu dispatch. No open
findings. New default test fails on old source, passes after fix. Full UI4008
pass, no skips; focused97 pass. Changed-file Biome and git diff checks pass.
No Python runtime change; Python suites, hardware and native Mac routing/pixels
not checked locally. This does not fix the separate typing-dispatch/Viewer-menu
audit findings. No workflow changes, no merge, native CI remains required.

CI follow-up: both Mac Python shards caught stale generated docs/KEYS.md,
test_keys_doc_is_up_to_date and test_every_doc_key_is_in_keymap. Regenerated
from canonical DEFAULT_KEYMAP (two changed cells, no handwritten workaround).
All three key-doc regression functions pass locally using stdlib harness;
no pytest/full-Python claim. Fresh CI on corrected head required.
