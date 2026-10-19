// What the Escape key does outside a drag: leave a text field first; else clear what is marked
// on the timeline (the clip selection, the lanes of a dragged range and the in and out marks,
// owner 2026-10-18); else go home (the timeline gets focus).

export function escapeAction({
  inTextField,
  selection,
  rangeTracks,
  inPoint,
  outPoint,
  trackSelection,
  rangeMode,
}) {
  if (inTextField) return "blur";
  // The track selection goes first (WP83): the next Esc clears the clips and the range.
  if ((trackSelection?.size ?? 0) > 0 || rangeMode === "selected") return "clear_tracks";
  const marked = (inPoint ?? null) !== null || (outPoint ?? null) !== null;
  if ((selection?.size ?? 0) > 0 || (rangeTracks?.size ?? 0) > 0 || marked) return "clear";
  return "home";
}
