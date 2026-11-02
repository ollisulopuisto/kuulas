# WP23a first slice: one stateful track effect (high-pass) with bypass

Merged into `main` with PR #91 on 2026-10-30; included in release candidate v26.10.30.1. This remains a partial WP23a implementation; callback profiling and listening are open.

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

## Review follow-up (callback caveats, supported route)
An audit review found the earlier wording "callback free of new blocking work" was
inaccurate. Corrected here:
- The first version created NumPy arrays for every sample and built filters on the
  first callback block. Now `FxState.prepare(project)` builds the filters on the
  control side (`Engine.set_project`), and the per-block loop uses plain floats (it still allocates per-block Python lists via `.tolist()`, so it is NOT allocation-free). An
  unprepared track still builds its filter on its first block (fallback).
- It is still a Python loop over every sample, so it is NOT real-time ready. Callback
  timing is unprofiled; native profiling on the Mac is an acceptance gate, along with
  listening. A vectorised or compiled filter may be needed.
- Supported configuration route: `ops.set_track(fx=[...])` only. There is no UI to add
  or edit a layer, so this is persisted-parameter plumbing, not a user-ready
  interactive effect.
