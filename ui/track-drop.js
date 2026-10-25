// Dragging a track header to a new place: pure maths, no DOM.

/**
 * The place a dragged track lands at, among the other tracks: how many of their header
 * midpoints (viewport y, top to bottom, the dragged one left out) lie above the pointer.
 * It is the `index` move_track takes (counted without the moved track).
 */
export function dropIndex(midpoints, y) {
  return midpoints.filter((mid) => mid < y).length;
}
