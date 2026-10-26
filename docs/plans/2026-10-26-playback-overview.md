# Playback and overview maintenance plan

Goal: fix startup cursor retreat and persistent manual-scroll detachment, and
move the overview's timestamps to a round adaptive scale at its top.

Evidence: live anchors repeat `playing: true`; render reset Follow on field
presence rather than a real transition. Startup slew also decayed while a future
audio anchor was stationary, moving the cursor against playback. Regression
samples showed 100480 -> 100478 frames at normal speed, with matching reverse
and fast failures. Overview quarter labels are replaced at the owner's request.

1. Write and fail clock startup, store previous-state and overview-scale tests.
2. Delay slew decay until the anchor begins advancing; provide previous state
   to store subscribers so render resets Follow only on real starts/stops.
3. Use round interior overview marks (at most four, fewer when narrow), reserve
   a top label band, and update English/Finnish help.
4. Run all UI tests, Ruff/Biome and required Python checks. Verify startup and
   manual scrolling in a synthetic browser session at multiple zoom levels.
5. Document and publish v26.10.26.4 with the already verified .26.3 security
   fixes. Keep the pushed .26.3 tag intact; do not publish it as the new build.

Red: eight new/updated checks failed before implementation. No existing test
or lint rule is relaxed. Quarter-position expectations intentionally change to
round timestamps as requested by the owner.

Validation: 3,556 UI tests passed after updating with current main's toolbar and
scripting features; Biome 2.2.4 and Ruff clean. Chrome reproduced the old Follow
reattachment, then verified persistent detachment at 480, 4,800 and 48,000 frames
per pixel, explicit Follow re-engagement, and the four top labels at 5/10/15/20
minutes on a 25-minute project. The combined release also passed the original
headless self-test, both recorder race regressions and documentation checks
(18 tests). Current-main Python plus the recorder fix: 5,133 passed.

Real audio-device startup is still an owner's confirmation; the startup clock
regressions use deterministic future-dated audio anchors at 1x, 1.5x and -1x.
The .26.3 tag was kept intact; its local DMG passed both self-tests but was not
published as Latest, so this release can include the reported regressions.
