# WP26 shuttle grains (overnight 2026-10-30)

Branch `wp26-shuttle-grains`, from main 49aaf177. Not merged, not released.

## What changed
- `src/kuulas/scrub_grains.py`: grain renderer (60 ms grains, 10 ms cosine
  crossfade). Grains always play forward; a negative speed only steps the read
  position back between grains.
- `src/kuulas/engine.py`: tape-rate runs with |speed| > 2 use grains instead of
  a soxr resampling of the mix. Speeds up to 2x are unchanged. The run uses the
  1:1 resampler key (as pitch-kept runs do). The playhead maths is unchanged.
- Tests: `tests/test_scrub_grains.py` (module), `tests/test_engine_grains.py`
  (pitch kept at +-3x/5x, playhead, end of run, backward, block-size
  independence). `test_engine_rate.py` reference and pitch tests now cover
  speeds up to 2x only; above that is the grain behaviour.

## Evidence
- Linux, sounddevice stubbed (no PortAudio): new and existing engine tests pass;
  ruff clean. See the CI result for the full suite.
- NOT native acceptance: nothing was listened to on a Mac. The grain size and
  crossfade are untuned by ear. Check by ear: speech at 3x and 5x, forward and
  backward, for clicks and for intelligibility.

## Not done
- Ruler drag does not yet scrub at pointer velocity (second WP26 gap).
- No DMG: building one needs the macOS workflow, held under the
  "no new GitHub costs" instruction.

## Ruler-drag velocity scrub (second WP26 gap): engine and API only
- `Engine.scrub(frame, velocity=None)`: stopped, with a pointer velocity of at
  least 0.25 programme-seconds per second, plays a ~90 ms burst in the drag's
  direction at that tape speed (capped at 5x; tape up to 2x, grains above).
  No velocity or too slow: the old fixed 60 ms burst. Playing: still a seek.
- `POST /api/transport` action `scrub` accepts optional `velocity`.
- `ui/scrub-velocity.js`: pure `dragVelocity(samples, rate)` with tests.
- Wired: a press and drag on the ruler (not on a marker flag) now scrubs.
  `ui/timeline.js` starts `createRulerScrub` (ui/scrub-velocity.js) on the
  press, feeds it pointer moves and sends `transport.scrub(frame, velocity)`
  at most every 30 ms; `ui/transport.js` moves the playhead at once and posts
  `scrub` with the velocity (while playing it stays a seek). `ui/app.js` passes
  `scrub` to the timeline.
- Checked in headless Chrome 156 against `kuulas open` on a 30 s tone (sounddevice
  stubbed, so no audio): a press sent `seek`, then a 12-step drag sent 12
  `scrub` posts with growing frames and a positive velocity (the sample drag
  was fast, so velocities were ~25-32 and the engine caps them at 5x). The
  screenshot during the drag shows the playhead following the pointer.
- NOT verified: that it sounds right. No audio was played; the engine path is
  covered by unit tests only. Whether a drag feels like tape (burst length,
  30 ms send rate, velocity smoothing over 80 ms) needs a listen on the Mac.
  A slow drag below 0.25x plays the old fixed burst.

## Provenance
This branch was rebuilt (reconstructed) from the original recorded edit scripts after
the first local branch was lost in an environment reset. The code is the same but the
commit hashes differ from the ones reported earlier (tip 9af40f5 had a WP23a load-meter
commit too, which is not part of this branch). Tests were re-run after the rebuild.
