// Moving clips by hand (owner, 2026-10-18): the edges snap to other clips' edges, the playhead
// and the marks, and holding a modifier makes the movement fine (a tenth of the pointer's
// travel). Pure; timeline.js applies it in updateClip. The radius is in pixels.
import { snapToPoints } from "./snap.js";

export const SNAP_PX = 8;
export const FINE_FACTOR = 0.1;

/** The delta after the pointer moved to `x`; fine movement scales only the new travel. */
export function advanceDelta({ delta, lastX }, x, { fine, zoom }) {
  const frames = (x - lastX) * zoom * (fine ? FINE_FACTOR : 1);
  return { delta: delta + frames, lastX: x };
}

/**
 * Where the moved block would land after snapping: { delta, at } with `at` the frame snapped
 * to (or null). `moved` are the clips' { start, end } before the move; the block's earliest
 * start and latest end are the edges that snap, the nearest to a target winning.
 */
export function snapMove({ moved, delta, targets, zoom, radiusPx = SNAP_PX }) {
  if (!moved?.length || !targets?.length) return { delta, at: null };
  const first = Math.min(...moved.map((c) => c.start));
  const last = Math.max(...moved.map((c) => c.end));
  const radius = radiusPx * zoom;
  let best = null;
  for (const edge of [first + delta, last + delta]) {
    const target = snapToPoints(edge, targets, radius);
    if (target === null) continue;
    const shift = target - edge;
    if (best === null || Math.abs(shift) < Math.abs(best.shift)) best = { shift, at: target };
  }
  return best === null ? { delta, at: null } : { delta: delta + best.shift, at: best.at };
}

/** Frames worth snapping to: other clips' edges, the playhead and the marks, sorted, unique. */
export function moveTargets(project, movedIds, { playhead, inPoint, outPoint }) {
  const skip = new Set(movedIds);
  const frames = new Set();
  for (const track of project?.tracks ?? []) {
    for (const clip of track.clips ?? []) {
      if (skip.has(clip.id)) continue;
      frames.add(clip.start);
      frames.add(clip.start + clip.length);
    }
  }
  for (const frame of [playhead, inPoint, outPoint]) {
    if (typeof frame === "number" && Number.isFinite(frame)) frames.add(frame);
  }
  return [...frames].sort((a, b) => a - b);
}

/** The { start, end } spans of the clips with these ids, before the move. */
export function movedSpans(project, ids) {
  const wanted = new Set(ids);
  const spans = [];
  for (const track of project?.tracks ?? []) {
    for (const clip of track.clips ?? []) {
      if (wanted.has(clip.id)) spans.push({ start: clip.start, end: clip.start + clip.length });
    }
  }
  return spans;
}
