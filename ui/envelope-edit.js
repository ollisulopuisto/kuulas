// ui/envelope-edit.js
// Envelope points on a clip's gain line. Plain ES module, no DOM, no imports.

/**
 * Inserts [frame, db] in sorted frame order.
 * If a point at an existing frame exists, replaces its db.
 * Returns a new array. Does not mutate the input.
 */
export function addPoint(envelope, frame, db) {
  const list = envelope ? envelope.map(([f, d]) => [f, d]) : [];
  const existingIndex = list.findIndex(([f]) => f === frame);
  if (existingIndex !== -1) {
    list[existingIndex] = [frame, db];
    return list;
  }
  const insertIndex = list.findIndex(([f]) => f > frame);
  if (insertIndex === -1) {
    list.push([frame, db]);
  } else {
    list.splice(insertIndex, 0, [frame, db]);
  }
  return list;
}

/**
 * Moves point at index to frame and db.
 * The frame is clamped between its neighbours' frames, never equal to or past them.
 * Throws Error for out-of-range index.
 * Returns a new array. Does not mutate the input.
 */
export function movePoint(envelope, index, frame, db) {
  if (
    !Array.isArray(envelope) ||
    typeof index !== "number" ||
    !Number.isInteger(index) ||
    index < 0 ||
    index >= envelope.length
  ) {
    throw new Error("Index out of range");
  }

  let minFrame = -Infinity;
  let maxFrame = Infinity;

  if (index > 0) {
    minFrame = envelope[index - 1][0] + 1;
  }
  if (index < envelope.length - 1) {
    maxFrame = envelope[index + 1][0] - 1;
  }

  let clampedFrame = frame;
  if (clampedFrame < minFrame) {
    clampedFrame = minFrame;
  }
  if (clampedFrame > maxFrame) {
    clampedFrame = maxFrame;
  }

  const result = envelope.map(([f, d]) => [f, d]);
  result[index] = [clampedFrame, db !== undefined ? db : envelope[index][1]];
  return result;
}

/**
 * Removes point at index.
 * Throws Error for out-of-range index.
 * Returns a new array. Does not mutate the input.
 */
export function removePoint(envelope, index) {
  if (
    !Array.isArray(envelope) ||
    typeof index !== "number" ||
    !Number.isInteger(index) ||
    index < 0 ||
    index >= envelope.length
  ) {
    throw new Error("Index out of range");
  }

  return envelope.filter((_, i) => i !== index).map(([f, d]) => [f, d]);
}

/**
 * Returns index of the closest point within radiusFrames (inclusive).
 * Ties break in favor of the earlier index.
 * Returns -1 when none is in range or inputs are invalid.
 */
export function nearestPoint(envelope, frame, radiusFrames) {
  return nearPoint(envelope, frame, radiusFrames);
}

/**
 * Linear interpolation in dB between neighbours.
 * Before the first point or after the last returns the nearest point's value.
 * With no points returns 0.
 * Does not mutate the input array.
 */
export function lineValueAt(points, frame) {
  if (!points || !Array.isArray(points) || points.length === 0) {
    return 0;
  }
  const last = points.length - 1;
  if (frame <= points[0][0]) {
    return points[0][1];
  }
  if (frame >= points[last][0]) {
    return points[last][1];
  }
  let low = 0;
  let high = last;
  while (high - low > 1) {
    const mid = (low + high) >> 1;
    if (points[mid][0] <= frame) {
      low = mid;
    } else {
      high = mid;
    }
  }
  const [f0, db0] = points[low];
  const [f1, db1] = points[high];
  if (f1 === f0) {
    return db1;
  }
  return db0 + ((db1 - db0) * (frame - f0)) / (f1 - f0);
}

/**
 * Returns index of the point nearest to frame within tolFrames.
 * Ties break in favor of the closer distance, or earlier index if equal.
 * Returns -1 if none is within tolFrames or inputs are invalid.
 * Does not mutate the input array.
 */
export function nearPoint(points, frame, tolFrames) {
  if (
    !Array.isArray(points) ||
    points.length === 0 ||
    typeof frame !== "number" ||
    !Number.isFinite(frame) ||
    typeof tolFrames !== "number" ||
    !Number.isFinite(tolFrames) ||
    tolFrames < 0
  ) {
    return -1;
  }

  let bestIndex = -1;
  let minDistance = Infinity;

  for (let i = 0; i < points.length; i++) {
    const pt = points[i];
    if (!Array.isArray(pt) || typeof pt[0] !== "number" || !Number.isFinite(pt[0])) {
      continue;
    }
    const dist = Math.abs(pt[0] - frame);
    if (dist <= tolFrames && dist < minDistance) {
      minDistance = dist;
      bestIndex = i;
    }
  }

  return bestIndex;
}

/**
 * Toggles a volume envelope point:
 * If a point is within tolFrames, it is removed (action: "removed").
 * Otherwise a point [frame, db] is inserted in order (action: "added")
 * with db clamped to -60..+12 and, when two points share the same frame,
 * the existing one replaced.
 * Does not mutate the input array.
 */
export function togglePoint(points, frame, db, tolFrames) {
  const idx = nearPoint(points, frame, tolFrames);
  if (idx !== -1) {
    return {
      points: points.filter((_, i) => i !== idx).map(([f, d]) => [f, d]),
      action: "removed",
    };
  }

  const clampedDb = Math.max(-60, Math.min(12, db));
  const list = points ? points.map(([f, d]) => [f, d]) : [];
  const existingIndex = list.findIndex(([f]) => f === frame);
  if (existingIndex !== -1) {
    list[existingIndex] = [frame, clampedDb];
  } else {
    const insertIndex = list.findIndex(([f]) => f > frame);
    if (insertIndex === -1) {
      list.push([frame, clampedDb]);
    } else {
      list.splice(insertIndex, 0, [frame, clampedDb]);
    }
  }

  return {
    points: list,
    action: "added",
  };
}
