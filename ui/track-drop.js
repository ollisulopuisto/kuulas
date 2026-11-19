// Dragging a track header to a new place: pure maths, no DOM.

/**
 * The place a dragged track lands at, among the other tracks: how many of their header
 * midpoints (viewport y, top to bottom, the dragged one left out) lie above the pointer.
 * It is the `index` move_track takes (counted without the moved track).
 */
export function dropIndex(midpoints, y) {
  return midpoints.filter((mid) => mid < y).length;
}

/** Translate a visible-row drop to the project's index, retaining hidden tracks. */
export function trackDropIndex(order, draggedId, visibleRows, y) {
  const rest = order.filter((id) => id !== draggedId);
  const visible = visibleRows
    .filter((row) => row.id !== draggedId && rest.includes(row.id))
    .toSorted((a, b) => a.midpoint - b.midpoint);
  const before = visible.find((row) => row.midpoint >= y);
  if (before) return rest.indexOf(before.id);
  const last = visible.at(-1);
  return last ? rest.indexOf(last.id) + 1 : order.indexOf(draggedId);
}
