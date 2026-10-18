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
  if (
    !Array.isArray(envelope) ||
    envelope.length === 0 ||
    typeof frame !== "number" ||
    !Number.isFinite(frame) ||
    typeof radiusFrames !== "number" ||
    !Number.isFinite(radiusFrames) ||
    radiusFrames < 0
  ) {
    return -1;
  }

  let bestIndex = -1;
  let minDistance = Infinity;

  for (let i = 0; i < envelope.length; i++) {
    const pt = envelope[i];
    if (!Array.isArray(pt) || typeof pt[0] !== "number" || !Number.isFinite(pt[0])) {
      continue;
    }
    const dist = Math.abs(pt[0] - frame);
    if (dist <= radiusFrames && dist < minDistance) {
      minDistance = dist;
      bestIndex = i;
    }
  }

  return bestIndex;
}
