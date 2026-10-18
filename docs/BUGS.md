# Owner's issue list

Everything the owner has raised stays here **until the owner says it is handled**. Only the owner
closes an item. Statuses: **open** (not fixed), **fixed, please check** (a fix is on main, waiting for
the owner to confirm), **closed** (the owner confirmed; moved to the bottom with the date).
Times are Helsinki. Add every new report here in the same session it is raised.

## Open

| # | Raised | Issue | Notes |
|---|---|---|---|
| 3 | 18.10 | Dropbox: the project lock must work with a synced folder (showstopper) | Built (per-host `locks/`, v26.10.18.63) but never tried against a real Dropbox. Move to "fixed, please check" after a real two-computer test. |

## Fixed, please check

| # | Raised | Issue | Fixed in |
|---|---|---|---|
| 4 | 18.10 | Exported WAVs would not play in Quick Look (RIFF size 0) | v26.10.18.58 |
| 5 | 18.10 | "Export all tracks" did not ask where to save | v26.10.18.59 |
| 6 | 18.10 | Esc should clear the clip selection but keep in/out marks | v26.10.18.57 |
| 7 | 18.10 | Speech tracks should be mono by default; stereo import asks | v26.10.18.60 |
| 8 | 18.10 | Alt-drag a region: the selection vanished on release | `e5925dd` (guess: the release event's Alt state); not seen on screen |
| 9 | 18.10 | After X (cut) the in/out markers and selection stayed drawn | cleared after cut, lift-cut, track cut and close gap (`edit-commands.js`) |
| 10 | 18.10 | "Select forward from selected clips, all tracks" selected every clip | `dd4e177` (clips starting at or after, not every overlapping clip) |
| 11 | 18.10 | Home/End (and other jumps) did not scroll the view to the playhead | `32a100b` |
| 12 | 18.10 | Buffer underrun when scrubbing back with J at multiple speed | `d8c5fe9` (the render loop re-mixed up to 489 times a block); not heard by the owner |
| 13 | 18.10 | Fast listening needed (stepless 1x to 2x, pitch kept, a toggle) | built, merged `da17d6f`; not heard by ear |
| 14 | 18.10 | Every command must be in a menu | menu coverage test, all 67 added |
| 15 | 18.10 | Left/Right should be Hindenburg-style fine cursor nudges (4 px at the current zoom; Shift 1 s, Alt 10 ms) | v26.10.18.64 |
| 16 | 18.10 | Tab and Shift+Tab did not always work: after a click on a track header the keys still thought the transcript had focus; word stops could be stale after edits | v26.10.18.64 |
| 17 | 18.10 | Tab scope: Alt+Tab cycles words / clip borders / sounds (replaces Shift+T on the Mac) | v26.10.18.64 |
| 18 | 18.10 | Right-click context menus on clips, ranges, empty lane and ruler | merged, not tried in a browser |
| 19 | 18.10 | X should work almost anywhere when in/out are marked | X, Shift+X, Alt+X and Alt+Mod+X now work from any panel (inspector, history, clipboard, markers, candidates) except text fields and the transcript, where X cuts the selected words |

## Closed

(none yet)
