// Where an open menu list goes so that it stays in the window. A submenu opens to the right of
// its parent list; when that runs past the window's right edge and the left side has room, it
// opens to the left. Any list whose bottom runs past the window's bottom moves up, but never
// above the margin. Pure, so the rule is tested without a layout engine.

/**
 * `box`: the list's rect as drawn; `parent`: the parent list's rect (submenus only);
 * `view`: { width, height } of the window. Returns { flipX, shiftY } in pixels, where
 * shiftY is zero or negative.
 */
export function placeMenu({ box, parent = null, view, margin = 8 }) {
  const flipX =
    parent !== null &&
    box.left + box.width > view.width - margin &&
    parent.left - box.width >= margin;
  const overflowY = box.top + box.height - (view.height - margin);
  const shiftY = overflowY > 0 ? Math.max(-overflowY, margin - box.top) : 0;
  return { flipX, shiftY };
}
