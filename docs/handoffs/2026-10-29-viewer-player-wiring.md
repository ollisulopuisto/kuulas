# Viewer transport wiring, still gated

First native checkpoint030724c7 passed reader/mixer7tests, Xcode build and
bundle checks (run40852111963). Preview artifact was delivered as no-audio,
ad-hoc timeline/Quick Look build, not finished player or notarized release.

Next change wires Play/Pause/Space, seek, node-clock position and edit/disappear
cleanup to the existing bounded queued player. Off-main open/decode; no mixing
on callback. Async setup and callbacks are revision-guarded so an edit switch
cannot resurrect old audio. Pure bounds tests cover empty/muted tail/end restart.

New reviewed synthetic golden covers stereo balance/downmix, mute, solo over
mute, bus gain/pan/master/mute, crossfades and muted-neighbor ramps. Python
regression binds it to real mixer; native tests compare whole and split windows.
Original golden untouched. All11portable Viewer tests and whole Ruff pass.

PlaybackEligibility still refuses every edit. Native compilation and these
broader tests must pass before relaxing that gate. Actual Mac launch, pixels,
seek/pause/end audition, Finder registration and sandbox media acceptance still
open. External linked audio remains refused. This is not a finished player.
No workflow/release/merge changes.
