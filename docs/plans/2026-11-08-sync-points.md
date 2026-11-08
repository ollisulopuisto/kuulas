# Sync Clips with Shared Sync Points

Implement the existing timeline shortcut for aligning two separately recorded clips
on a sound that appears in both recordings. Capture the source frame under the
playhead, keep it as temporary UI state, and use the next capture as the reference
point. Align the second clip and mark the source files in sync in one undoable edit.

## Scope

- Add a pure `align_points` project operation with source-frame validation.
- Wire `Alt+Mod+1` into a two-press flow: first capture, then align the next clip.
- Explain the pending point and completion in English and Finnish; draw the pending
  point on the timeline.
- Test the operation, command behavior, and menu/key discoverability before coding.

This first slice aligns a fixed offset. Detecting and correcting drift from a second
point, and automatic waveform alignment, remain in WP16.
