// ui/snap.js
// Snapping a time to a grid or to nearby points. Plain ES module, no DOM, no imports.

/**
 * Snaps frame to the nearest point within radius frames (inclusive).
 * Ties break in favor of the smaller point.
 * Returns null when none is in range, points is empty or missing,
 * or radius is not a finite number >= 0.
 */
export function snapToPoints(frame, points, radius) {
  if (typeof frame !== "number" || !Number.isFinite(frame)) {
    return null;
  }
  if (!Array.isArray(points) || points.length === 0) {
    return null;
  }
  if (typeof radius !== "number" || !Number.isFinite(radius) || radius < 0) {
    return null;
  }

  let bestPoint = null;
  let minDistance = Infinity;

  for (const p of points) {
    if (typeof p !== "number" || !Number.isFinite(p)) {
      continue;
    }
    const dist = Math.abs(p - frame);
    if (dist <= radius) {
      if (dist < minDistance) {
        minDistance = dist;
        bestPoint = p;
      } else if (dist === minDistance && p < bestPoint) {
        bestPoint = p;
      }
    }
  }

  return bestPoint;
}

/**
 * Snaps frame to the nearest grid line: Math.round(frame / step) * step (halves round up).
 * Returns frame unchanged when step is not a finite positive number.
 */
export function snapToGrid(frame, step) {
  if (typeof step !== "number" || !Number.isFinite(step) || step <= 0) {
    return frame;
  }
  if (typeof frame !== "number" || !Number.isFinite(frame)) {
    return frame;
  }
  const result = Math.round(frame / step) * step;
  return Object.is(result, -0) ? 0 : result;
}

/**
 * Snaps frame to points or grid. Points win over the grid;
 * if neither applies, returns frame.
 * No input is mutated.
 */
export function snap(frame, options = {}) {
  const { points, radius, step } = options ?? {};
  const point = snapToPoints(frame, points, radius);
  if (point !== null) {
    return point;
  }
  return snapToGrid(frame, step);
}
