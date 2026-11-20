# Automatic sync implementation, 20 November 2026

The owner requested sync for separately recorded remote participants, including
recordings delivered in multiple pieces. The approved UI is a full-window timing
review mode, not an immediate edit or a modal. The user arranges files in order
on participant tracks before starting.

## Implemented in this branch

- Channel-power RMS envelopes at 1 ms, bounded ten-second channel-first reads,
  whole-reference coarse FFT search and bounded fine correlation. Absolute
  correlation and competing-peak checks reject weak or repetitive matches.
- Conservative offset/drift consensus across independent windows. A fixed start
  move is proposed only when all measured windows fit and the total drift is
  within 4 ms. Drift is reported, never described as corrected by a single move.
- Track-unit analysis checks every piece. A missing, partial, unmatched or
  inconsistent piece prevents a whole-track sound proposal. Multiple source
  files keep their timeline order and gaps; no filename-order guessing.
- Auto tries shared sound first. Turn-gap analysis uses speechmix activity,
  shared recorded coverage and turn handoffs, not minimum overlap alone.
  Gap alternatives are always manual choices, never confidence percentages.
- Full-window review has actual source waveforms, whole-track drag by default,
  explicit individual-piece movement, a numeric offset and 10 ms nudges,
  zoom, seek, loop, original/proposal listening and reset to suggestion.
- Preview is a server-owned frozen Project with timing changes only. Engine
  listening-source replacement plays it without editing history. Apply commits
  that same plan once. Cancel discards it. Normal API writes and history edits
  are blocked during the mode; stale snapshots and invalid moves fail closed.
- New movement does not overwrite another piece or cross project frame zero.
  Original media, source offsets, fades, envelopes and file order stay intact.
- Analysis runs through the existing read-only worker/background job system.
  Cancellation and job completion cannot apply to a replacement review.
- Menu, command palette, shortcut (Alt+Mod+Shift+F7), English/Finnish strings
  and help are part of the workflow.

## Explicit limits and verification still required

Continuous drift is not resampled or stretched. Discontinuous pieces are not
split automatically: the review reports disagreement and permits explicit
piece moves. This follows the approved no-resampling design, replacing the
older resampled-variant plan. Existing sync-group metadata is not silently
redefined by this timing edit. A separate intentional mark-in-sync command
remains available after leaving the mode.

Synthetic tests and browser checks do not establish accuracy on the owner's
actual remote recordings. Native Mac audio, real output devices and the
packaged application are untested here. CI is the only Mac compiler.

No version, changelog, roadmap or PLAN status change belongs to this branch.
