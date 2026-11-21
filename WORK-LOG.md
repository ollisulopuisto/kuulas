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
