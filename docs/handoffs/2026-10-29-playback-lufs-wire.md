# Playback LUFS wire fix

Cause: Engine.meter already returns the shared three-second K-weighted loudness
of the actual device output, but server.meter_message dropped it by whitelisting
four peak fields. The existing bottom LUFS bar/readout therefore stayed pending.

Fix forwards short_term as a rounded LUFS value, preserves warmup None and the
silence/stop floor. Peak clipping remains independent. No DSP duplication,
new meter layout, or recording-meter changes.

Two regression tests failed for missing short_term before the fix. The server,
engine, output-meter and shared short-term suites pass: 191 tests. The local
PortAudio shared library was supplied through find_library in the test runner,
not a production change. Ruff/diff clean. Real Chromium component fixture
inspected Finnish/dark warmup and moving -22.3/-17.1 LUFS bar/readout, floor
reset. Fixture proof is not native audio-device listening acceptance.

Suggested release note: Restore the live three-second LUFS bar and readout by
forwarding output loudness over the live channel, not only peak samples.
