// Waveform display scale and normalisation (WP52). Pure logic, no DOM.

/**
 * Returns the peak value of the peaks array at the given percentile (nearest rank).
 *
 * @param {number[]} peaks - Array of non-negative numbers (0 to 1).
 * @param {number} [percentile=0.99]
 * @returns {number}
 */
export function peakOf(peaks, percentile = 0.99) {
  if (!peaks || peaks.length === 0) return 0;
  const sorted = [...peaks].sort((a, b) => a - b);
  if (sorted[sorted.length - 1] === 0) return 0;
  const rank = Math.ceil(percentile * sorted.length);
  const index = Math.min(sorted.length - 1, Math.max(0, rank - 1));
  return sorted[index];
}

/**
 * Calculates the waveform scaling factor.
 *
 * @param {number[]} peaks
 * @param {Object} [options]
 * @param {string} [options.mode="true"] - "true", "normalised", or "loudest"
 * @param {number} [options.loudest=1]
 * @param {number} [options.floor=0.001]
 * @param {number} [options.maxGain=40]
 * @returns {number}
 */
export function scaleFactor(
  peaks,
  { mode = "true", loudest = 1, floor = 0.001, maxGain = 40 } = {},
) {
  if (mode === "true") return 1;
  const peak = peakOf(peaks);
  if (peak < floor) return 1;

  let factor = 1;
  if (mode === "normalised") {
    factor = 1 / peak;
  } else if (mode === "loudest") {
    if (loudest < floor) return 1;
    factor = 1 / loudest;
  }

  return Math.min(factor, maxGain);
}

/**
 * Returns display label for a scale factor.
 * Returns null for factors within 1% of 1 (0.99 <= factor <= 1.01).
 *
 * @param {number} factor
 * @returns {string | null}
 */
export function labelFor(factor) {
  if (factor >= 0.99 && factor <= 1.01) {
    return null;
  }
  return `x${factor.toFixed(1)}`;
}

/**
 * Returns dB text for a factor with one decimal and sign always shown.
 *
 * @param {number} factor
 * @returns {string}
 */
export function dbText(factor) {
  const db = 20 * Math.log10(factor);
  const formatted = db.toFixed(1);
  if (formatted === "-0.0" || formatted === "0.0") {
    return "+0.0 dB";
  }
  if (db > 0) {
    return `+${formatted} dB`;
  }
  return `${formatted} dB`;
}
