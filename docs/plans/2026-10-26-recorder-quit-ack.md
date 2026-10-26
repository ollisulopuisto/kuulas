# Recorder quit acknowledgement plan

Goal: fix the Linux headless self-test failure without hiding it or retrying it.

Evidence: CI run 40314163020, Ubuntu job 121542445747, reports only
`FAIL recorder: RecorderError: disconnected`. `cmd_quit` requested shutdown
before its response was queued; the main thread could close every socket first.

1. Force that ordering in a recorder regression and observe the exact disconnect.
2. Carry a shutdown action with the accepted quit reply in the bounded sender
   queue; run it after sending, including on delivery failure. Preserve busy refusal.
3. Verify recorder/bundle tests and the full suite. Improve the headless assertion
   so the failed self-test's output is included directly in its assertion message.
4. Integrate with the already verified UI fixes for v26.10.26.4, then tag/build.

Red: forced immediate-close regression failed with `RecorderError: disconnected`.
Green: all 45 recorder/bundle tests passed, including failed-send handling and the
real fake-source headless recording. Ruff is clean. No rule, assertion or check
was removed; no real microphone or playback device was opened.

Final full-suite run on current main plus this fix: 5,133 passed, one existing
Starlette deprecation warning, in 1,832.18 seconds. Ruff clean. Both deterministic
race cases also passed after making connection registration explicit in their setup.
