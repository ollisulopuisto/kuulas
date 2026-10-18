// ui/track-order.js
// Track order manipulation. Plain ES module, no DOM, no imports.

/**
 * Moves track id by delta places, clamped at both ends (0..order.length - 1).
 * Throws Error for unknown id.
 * Pure and returns a new array. Does not mutate order.
 */
export function moveTrack(order, id, delta) {
  if (!Array.isArray(order)) {
    throw new Error("Invalid order");
  }
  const currentIndex = order.indexOf(id);
  if (currentIndex === -1) {
    throw new Error(`Unknown track id: ${id}`);
  }

  const targetIndex = Math.max(0, Math.min(order.length - 1, currentIndex + delta));
  if (targetIndex === currentIndex) {
    return [...order];
  }

  const result = [...order];
  result.splice(currentIndex, 1);
  result.splice(targetIndex, 0, id);
  return result;
}

/**
 * Moves track id to specified index, clamped to 0..order.length - 1.
 * Throws Error for unknown id.
 * Pure and returns a new array. Does not mutate order.
 */
export function moveToIndex(order, id, index) {
  if (!Array.isArray(order)) {
    throw new Error("Invalid order");
  }
  const currentIndex = order.indexOf(id);
  if (currentIndex === -1) {
    throw new Error(`Unknown track id: ${id}`);
  }

  const targetIndex = Math.max(0, Math.min(order.length - 1, index));
  if (targetIndex === currentIndex) {
    return [...order];
  }

  const result = [...order];
  result.splice(currentIndex, 1);
  result.splice(targetIndex, 0, id);
  return result;
}

/**
 * Moves the ids that are in order together by delta, keeping their relative order.
 * Blocked as a whole at either end.
 * Ids not in order are ignored; empty ids returns a copy.
 * Pure and returns a new array. Does not mutate order.
 */
export function moveBlock(order, ids, delta) {
  if (!Array.isArray(order)) {
    return [];
  }
  if (!Array.isArray(ids) || ids.length === 0 || delta === 0) {
    return [...order];
  }

  const idSet = new Set(ids);
  const selectedIndices = [];
  for (let i = 0; i < order.length; i++) {
    if (idSet.has(order[i])) {
      selectedIndices.push(i);
    }
  }

  if (selectedIndices.length === 0) {
    return [...order];
  }

  const minIdx = selectedIndices[0];
  const maxIdx = selectedIndices[selectedIndices.length - 1];

  let effectiveDelta = delta;
  if (delta < 0) {
    effectiveDelta = Math.max(delta, -minIdx);
  } else if (delta > 0) {
    effectiveDelta = Math.min(delta, order.length - 1 - maxIdx);
  }

  if (effectiveDelta === 0) {
    return [...order];
  }

  const result = new Array(order.length);
  const newSelectedIndices = new Set();

  for (const idx of selectedIndices) {
    const newIdx = idx + effectiveDelta;
    result[newIdx] = order[idx];
    newSelectedIndices.add(newIdx);
  }

  const unselected = order.filter((id) => !idSet.has(id));
  let unselectedIdx = 0;
  for (let i = 0; i < result.length; i++) {
    if (!newSelectedIndices.has(i)) {
      result[i] = unselected[unselectedIdx++];
    }
  }

  return result;
}

/**
 * Returns true when the two arrays differ in order or length.
 */
export function isReordered(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) {
    return true;
  }
  if (a.length !== b.length) {
    return true;
  }
  return a.some((val, i) => val !== b[i]);
}
