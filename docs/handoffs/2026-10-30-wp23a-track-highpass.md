# WP23a first slice: one stateful track effect (high-pass) with bypass

Branch `wp23a-track-highpass`, from main 49aaf177. Separate from the WP26 work.

- `src/kuulas/fx.py`: causal RBJ high-pass biquad (20-400 Hz), `FxState` with
  running state per track layer, `process_whole` reference.
- `model.FxLayer` and `Track.fx`: saved with the project; absent from the file
  when empty (old projects keep their bytes). `ops.set_track(fx=[...])` validates
  kind and cutoff.
- `mixer.mix(..., fx=)`: applied as an insert before gate and gain, only when a
  live `FxState` is passed. Exports and all other readers play dry.
- Engine: live state, reset on every new run or seek; applied at 1x forward
  plain playback only (no skips/loops, no tape-rate, stretch or backward runs yet).
- Bypass returns the dry signal exactly and leaves the state at rest.
- Tests (tests/test_fx.py): output identical for any block split, bypass dry,
  seek and off/on restart from silence, persistence, validation, mixer and engine.
- Not done: no UI to add or edit a layer, no plugins, no latency compensation
  (a biquad adds none; a delayed parallel path needs its own impulse-alignment
  test first), export does not apply layers.
- Not verified: callback timing and listening on the Mac (acceptance gates).
  Tests ran on Linux with sounddevice stubbed; 5 sandbox "missing tool" tests fail
  the same on plain main.
