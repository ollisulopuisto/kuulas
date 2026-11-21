# Work log

## 2026-11-21: WP25 report audibility

Branch `fix/music-report-audibility`. No UI or playback change. Seven initial
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
