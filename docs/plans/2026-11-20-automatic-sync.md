# Automatic sync implementation, 20 November 2026

The owner requested automatic alignment of separately recorded remote tracks.
The existing correlator and manual sync points do not fulfill that request.
This branch is incomplete until the user can run the workflow safely.

## Measurement core

- Compute channel-power RMS envelopes at 1 ms. Stereo phase cancellation must
  not erase the reference. Callers must transpose MediaStore's channel-first
  arrays before passing them to the frame-first envelope function.
- Search the entire reference independently for every coarse window, so a
  twenty-minute local can begin fifteen minutes into an hour-long call and a
  dropout can change its lag halfway through.
- Refine a clear coarse match to milliseconds in a bounded local search.
- Require an absolute correlation floor as well as the competing-peak ratio.
  A unique but tiny random peak is not evidence of shared audio.
- Use zero-padded FFT convolution. Do not perform quadratic direct convolution
  over a long call. Yield at window boundaries to the playback priority gate.

Synthetic tests cover a 2.345 s offset, 100 ppm clock drift, a removed 1.2 s
interval, unrelated audio, silence, periodic ambiguity, opposite-phase stereo,
and the long-reference/short-local case. These test measurements, not a finished
editing workflow or resampling correction.

## Remaining work

1. Convert clear measurements to a conservative proposal. Require independent
   supporting windows, robustly fit drift, and separate discontinuities from
   clock drift. Never move an unmatched or ambiguous clip.
2. Refine each discontinuity before picking a quiet split. Merely picking the
   quietest point between sparse windows could misalign seconds of speech.
3. Read selected source audio in bounded chunks in the existing analysis worker.
   Keep heavy work out of the editor process. Include offline-media, read-only,
   cancellation and memory limits.
4. Make drift-corrected variants without altering originals. The existing
   ops.use_variant deliberately requires equal source/variant lengths, so do
   not reuse it for a different-length resample. Preserve source offsets,
   transcript timings, mute/gate ranges, fades and media provenance explicitly.
5. Apply the entire accepted proposal as one undo step. Protect it with a
   project-snapshot key. Preserve existing sync partners and use the topmost
   selected track as the reference. Do not overwrite unrelated clips silently.
6. Run a background measurement job, show per-clip offsets, drift and split
   decisions, and respect the owner's confirmation-before-moving setting.
   Wire Alt+Mod+G and menu/palette/help only when the full route is tested.
7. Test actual session/export behavior separately from synthetic source tests.
   A local browser cannot prove a native Mac audio or recording-device path.

No version, changelog, roadmap or plan-status change is part of this work.
