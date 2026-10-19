/**
 * Peak hold and decay tracker for record level meters.
 *
 * Tracks displayed bar level and held peak in dBFS with configurable hold and decay.
 */

export function createPeakHold({ holdMs = 1500, decayDbPerS = 20, floorDb = -60 } = {}) {
  let bar = floorDb;
  let peak = floorDb;
  let clipped = false;
  let lastT = null;
  let peakSetT = null;

  return {
    update(levelDb, t) {
      if (typeof levelDb === "number" && levelDb > 0) {
        clipped = true;
      }

      let clampedLevel = floorDb;
      if (typeof levelDb === "number" && Number.isFinite(levelDb)) {
        clampedLevel = Math.max(floorDb, Math.min(0, levelDb));
      }

      const dt = lastT !== null && t > lastT ? t - lastT : 0;

      // Update bar: jumps up immediately, falls at decayDbPerS
      if (clampedLevel >= bar) {
        bar = clampedLevel;
      } else {
        const barDecay = (decayDbPerS * dt) / 1000;
        bar = Math.max(clampedLevel, bar - barDecay);
      }
      bar = Math.max(floorDb, Math.min(0, bar));

      // Update peak: jumps up immediately and resets hold, stays for holdMs then falls at decayDbPerS
      if (clampedLevel >= peak) {
        peak = clampedLevel;
        peakSetT = t;
      } else {
        if (peakSetT === null) {
          peakSetT = t;
        }
        const holdEnd = peakSetT + holdMs;
        if (t > holdEnd) {
          const prevT = lastT !== null ? lastT : t;
          const decayStart = Math.max(prevT, holdEnd);
          const decayMs = Math.max(0, t - decayStart);
          const peakDecay = (decayDbPerS * decayMs) / 1000;
          peak = Math.max(clampedLevel, peak - peakDecay);
        }
      }
      peak = Math.max(floorDb, Math.min(0, peak));

      if (lastT === null || t > lastT) {
        lastT = t;
      }

      return { bar, peak, clipped };
    },

    clearClip() {
      clipped = false;
    },

    reset() {
      bar = floorDb;
      peak = floorDb;
      clipped = false;
      lastT = null;
      peakSetT = null;
    },
  };
}
