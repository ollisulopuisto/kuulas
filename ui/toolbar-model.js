// The toolbar's layout (WP86, docs/design/TOOLBAR.md): an ordered list of command ids, and the
// pure functions that change it. The owner's rule is that a button's place never changes unless
// the user changes it, so the only functions here are the user's own acts (pin, unpin, move, reset)
// and none of them takes a use count, a state or a hint. A layout is the order; there is nothing
// else to drift.

/** The first ten, by workflow: undo, redo, import, transcribe, Auto-Silence, split, mute, sync, mix, export. */
export const DEFAULT_LAYOUT = Object.freeze([
  "edit.undo",
  "edit.redo",
  "app.import",
  "app.transcribe",
  "app.auto_silence",
  "edit.split",
  "clip.mute",
  "sync.resync_range",
  "export.automix",
  "app.export",
]);

/** The default order as a new list, for "Reset toolbar". */
export const resetLayout = () => [...DEFAULT_LAYOUT];

const clamp = (index, length) => Math.max(0, Math.min(index, length));

/** Add `id` at the end, or at `at`. A button already there is left where it is (same list back). */
export function pinButton(layout, id, at = layout.length) {
  if (layout.includes(id)) return layout;
  const next = [...layout];
  next.splice(clamp(at, next.length), 0, id);
  return next;
}

/** Remove `id`; the others keep their order. */
export function unpinButton(layout, id) {
  return layout.includes(id) ? layout.filter((item) => item !== id) : layout;
}

/** Put `id` at position `to` of the list that remains without it. */
export function moveButton(layout, id, to) {
  if (!layout.includes(id)) return layout;
  const rest = layout.filter((item) => item !== id);
  rest.splice(clamp(to, rest.length), 0, id);
  return rest;
}

/**
 * Where a dragged button lands: `mids` are the vertical centres of the buttons in the layout and
 * `y` the pointer. The result is the index in the list without the dragged button (`from`), the
 * form `moveButton` takes.
 */
export function dropIndex(mids, from, y) {
  const others = mids.filter((_, i) => i !== from);
  let to = 0;
  while (to < others.length && y > others[to]) to += 1;
  return to;
}

/** One place up (-1) or down (+1), the keyboard way. The same list at an end or for an unknown id. */
export function stepButton(layout, id, delta) {
  const at = layout.indexOf(id);
  const to = at + delta;
  if (at < 0 || to < 0 || to >= layout.length) return layout;
  return moveButton(layout, id, to);
}

/**
 * What was stored, made safe: the known commands in the stored order, each once. A command that
 * no longer exists is dropped and the others stay where they were. Not a list: the default.
 * An empty list is kept, because the user may have removed every button.
 */
export function normalizeLayout(stored, known) {
  if (!Array.isArray(stored)) return resetLayout();
  const seen = new Set();
  const out = [];
  for (const id of stored) {
    if (typeof id !== "string" || !known.has(id) || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  return out;
}

/**
 * The rows of the right-click menu on a command (a menu row) or a toolbar button: Add to the
 * toolbar when it is not there, Remove when it is. Shaped for context-menu.js.
 */
export function toolbarMenuItems(id, layout) {
  return layout.includes(id)
    ? [{ id: "unpin", labelKey: "ui.rail.menu.remove", enabled: true }]
    : [{ id: "pin", labelKey: "ui.rail.menu.add", enabled: true }];
}

/** What picking `pick` from that menu does to `layout`: a pin goes to the end, a remove leaves the order. */
export function applyToolbarMenu(layout, id, pick) {
  if (pick === "pin") return pinButton(layout, id);
  if (pick === "unpin") return unpinButton(layout, id);
  return layout;
}

/** A deliberate drag-away needs 40 px beyond the rail; nearby drops remain reorders. */
export function outsideRail(rect, x, y, margin = 40) {
  return (
    x < rect.left - margin ||
    x > rect.right + margin ||
    y < rect.top - margin ||
    y > rect.bottom + margin
  );
}
