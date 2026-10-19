/**
 * Live waveform columns while recording (T63, WP12a).
 *
 * Sliding window of linear peak columns (0..1) for drawing a live waveform display.
 */

export function createLiveWave({ columns } = {}) {
  if (typeof columns !== "number" || !Number.isFinite(columns) || columns < 1) {
    throw new RangeError("columns must be a number >= 1");
  }

  const limit = Math.floor(columns);
  const peaks = [];

  return {
    push(peak) {
      let val = Number(peak);
      if (Number.isNaN(val)) {
        val = 0;
      } else {
        val = Math.max(0, Math.min(1, val));
      }

      peaks.push(val);
      if (peaks.length > limit) {
        peaks.shift();
      }
    },

    snapshot() {
      return peaks.slice();
    },

    reset() {
      peaks.length = 0;
    },
  };
}
