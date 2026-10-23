// Reordering the Clipboard list by dragging an entry onto another row (owner, 2026-10-23,
// BUGS #115). The list is the order shown and the order Paste reads, so a drop is one move:
// before some row, or last. Pure; the panel draws the insertion line and sends the move.

/**
 * Where the dragged entry goes when dropped at `offsetY` inside the row `rowId` (`rowHeight`
 * tall) of the list `ids` (top to bottom): { before: id | null } (null: last), or null when
 * nothing would change (it is dropped where it already is) or when the entry is not in this
 * list (a drag from another shelf is a paste, not a reorder).
 */
export function reorderTarget({ draggedId, rowId, offsetY, rowHeight, ids }) {
  const from = ids.indexOf(draggedId);
  const row = ids.indexOf(rowId);
  if (from < 0 || row < 0) return null;
  const upper = offsetY < rowHeight / 2;
  const slot = upper ? row : row + 1; // the index the entry would be inserted before
  if (slot === from || slot === from + 1) return null;
  return { before: slot >= ids.length ? null : ids[slot] };
}
