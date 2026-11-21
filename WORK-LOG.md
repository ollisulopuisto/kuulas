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
