// Pointer-hover decisions for the in-window menu bar (menubar.js). Pure: no DOM, no timers.
// The bar asks what to do and does it. Mac-like: with a menu open, another title opens at
// once; a submenu opens after the pointer rests on its row, and closes when the pointer
// moves to another row (after a short grace when it is travelling toward the submenu).

export const HOVER_DELAY = 200; // ms

/** Only a mouse hovers. Touch and pen get the click and keyboard behaviour only. */
export function isHoverPointer(pointerType) {
  return pointerType === "mouse";
}

/** The pointer is over a top-level title: "open" it, or "none". A closed bar never opens. */
export function topHover({ open, top, target }) {
  return open && top !== target ? "open" : "none";
}

/**
 * The pointer is over a row of the open menu's list (not inside the submenu).
 * Returns {act: "cancel"} (drop any pending change), or {act: "open-sub" | "close-sub", delay}.
 * `towardSub`: the pointer is heading for the open submenu, so a close is only delayed.
 */
export function rowHover({ subOpen, openRow, row, rowIsSubmenu, towardSub }) {
  if (rowIsSubmenu) {
    if (subOpen && openRow === row) return { act: "cancel" };
    return { act: "open-sub", delay: HOVER_DELAY };
  }
  if (!subOpen) return { act: "cancel" };
  return { act: "close-sub", delay: towardSub ? HOVER_DELAY : 0 };
}

/**
 * Is the move from `prev` to `cur` heading for the submenu `rect`? True when `cur` lies in
 * the triangle from `prev` to the submenu's near edge (the classic diagonal-movement test).
 */
export function movingToward(prev, cur, rect) {
  if (!prev || !rect) return false;
  const edge = rect.left >= cur.x ? rect.left : rect.right;
  const b = { x: edge, y: rect.top };
  const c = { x: edge, y: rect.bottom };
  const side = (p, q, r) => (p.x - r.x) * (q.y - r.y) - (q.x - r.x) * (p.y - r.y);
  const d1 = side(cur, prev, b);
  const d2 = side(cur, b, c);
  const d3 = side(cur, c, prev);
  const neg = d1 < 0 || d2 < 0 || d3 < 0;
  const pos = d1 > 0 || d2 > 0 || d3 > 0;
  return !(neg && pos);
}
