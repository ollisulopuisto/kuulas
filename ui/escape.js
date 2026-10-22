// What the Escape key does outside a drag, a dialog and the panels' own fields: ONE transient
// layer per press, innermost first, never two things and never anything destructive (owner,
// 2026-10-22). The layers, in order:
//   1. the Auto-Silence live preview (discarded at once, from anywhere; nothing was committed);
//   2. a text field (blurred);
//   3. the track selection (header clicks, "selected tracks only");
//   4. the clip selection, the dragged range's lanes and the in and out marks (together);
//   5. focus mode (left);
//   6. otherwise "home": the timeline gets the focus.
// Whatever the layer, the press ends with the timeline focused (runEscape).
// Not here: a transcript word range (the transcript collapses it and stops the key), a running
// export (only its Cancel button stops it), playback and previews (Space and K stop those).

export function escapeAction({
  inTextField,
  selection,
  rangeTracks,
  inPoint,
  outPoint,
  trackSelection,
  rangeMode,
  focusMode = null,
  silencePreview = false,
}) {
  // A preview is a transient layer on top of everything else; closing it commits nothing.
  if (silencePreview) return "discard_preview";
  if (inTextField) return "blur";
  // The track selection goes first (WP83): the next Esc clears the clips and the range.
  if ((trackSelection?.size ?? 0) > 0 || rangeMode === "selected") return "clear_tracks";
  const marked = (inPoint ?? null) !== null || (outPoint ?? null) !== null;
  if ((selection?.size ?? 0) > 0 || (rangeTracks?.size ?? 0) > 0 || marked) return "clear";
  // Focus mode is a deliberate view: Esc peels the marks first, then leaves it.
  if (focusMode) return "leave_focus";
  return "home";
}

/**
 * Do one escape step. `input` is what escapeAction reads; `fx` has the effects:
 * { blur, discardPreview, clearTracks, clearMarks, leaveFocus, focusTimeline }.
 * Exactly one layer is peeled, then the timeline takes the focus (also after "clear", which used
 * to leave the focus where it was). Returns the step taken.
 */
export function runEscape(input, fx) {
  const what = escapeAction(input);
  if (what === "discard_preview") fx.discardPreview();
  else if (what === "blur") fx.blur();
  else if (what === "clear_tracks") fx.clearTracks();
  else if (what === "clear") fx.clearMarks();
  else if (what === "leave_focus") fx.leaveFocus();
  fx.focusTimeline();
  return what;
}
