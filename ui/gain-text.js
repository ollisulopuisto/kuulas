/**
 * Formats a clipping amount in dB as a short badge text.
 *
 * @param {number} overDb
 * @returns {string}
 */
export function levelBadge(overDb) {
  if (typeof overDb !== "number" || !Number.isFinite(overDb) || overDb <= 0) {
    return "";
  }
  if (overDb > 99.9) {
    return "+99.9";
  }
  return `+${overDb.toFixed(1)}`;
}

/**
 * Calculates the next gain value when nudged by a key.
 *
 * @param {number} db
 * @param {number} direction - > 0 for up, < 0 for down, 0 to stay
 * @param {boolean} [fine=false] - fine step (0.1 dB) vs normal step (0.5 dB)
 * @returns {number}
 */
export function gainSteps(db, direction, fine = false) {
  const current = typeof db === "number" && Number.isFinite(db) ? db : 0;
  const step = fine ? 0.1 : 0.5;

  let dir = 0;
  if (direction > 0) {
    dir = 1;
  } else if (direction < 0) {
    dir = -1;
  }

  const raw = current + dir * step;
  const rounded = Math.round(raw * 10) / 10 + 0;
  return Math.max(-60, Math.min(12, rounded));
}
