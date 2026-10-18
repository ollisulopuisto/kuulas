// What the Escape key does outside a drag: leave a text field first; else clear the clip
// selection (and the lanes of a dragged range) but never the in and out marks; else go home
// (the timeline gets focus).

export function escapeAction({ inTextField, selection, rangeTracks }) {
  if (inTextField) return "blur";
  if ((selection?.size ?? 0) > 0 || (rangeTracks?.size ?? 0) > 0) return "clear";
  return "home";
}
