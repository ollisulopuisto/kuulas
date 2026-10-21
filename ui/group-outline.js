// A clip group (Clip.group, Edit > Group) reads as one object on the timeline: one outer
// outline round all its members, across tracks (owner, 2026-10-21). Distinct from the
// selection (2 px, on the clip's own border) and from the dashed amber edges of a closed
// stretch: a 1 px rounded line in --signal-group, GROUP_OUTSET px outside the bodies.
// Spec: docs/design/SILENCE-VISUALS.md "Groups". Pure: timeline.js draws the boxes.

/** How far outside the clip bodies the group line runs (inside the 2 px lane inset). */
export const GROUP_OUTSET = 1.5;
/** Clip bodies stand this far inside their lane (paint.js BODY_INSET). */
const BODY_INSET = 2;

/**
 * [{ group, x, y, w, h }] in canvas pixels: one box per group with two or more members laid
 * out in `rows` (layoutFor's rows; a collapsed track has none, so its members do not count).
 * `view` = { scroll, zoom, scrollY, rulerHeight }.
 */
export function groupOutlines(project, rows, view) {
  const rowOf = new Map(rows.filter((row) => row.kind === "track").map((row) => [row.id, row]));
  const boxes = new Map();
  for (const track of project?.tracks ?? []) {
    const row = rowOf.get(track.id);
    if (!row) continue;
    const top = view.rulerHeight + row.top - view.scrollY + BODY_INSET;
    const bottom = top + row.height - 2 * BODY_INSET;
    for (const clip of track.clips ?? []) {
      if (!clip.group) continue;
      const left = (clip.start - view.scroll) / view.zoom;
      const right = (clip.start + clip.length - view.scroll) / view.zoom;
      const box = boxes.get(clip.group);
      if (!box) {
        boxes.set(clip.group, { count: 1, left, right, top, bottom });
        continue;
      }
      box.count += 1;
      box.left = Math.min(box.left, left);
      box.right = Math.max(box.right, right);
      box.top = Math.min(box.top, top);
      box.bottom = Math.max(box.bottom, bottom);
    }
  }
  const out = [];
  for (const [group, box] of boxes) {
    if (box.count < 2) continue;
    out.push({
      group,
      x: box.left - GROUP_OUTSET,
      y: box.top - GROUP_OUTSET,
      w: box.right - box.left + 2 * GROUP_OUTSET,
      h: box.bottom - box.top + 2 * GROUP_OUTSET,
    });
  }
  return out;
}
