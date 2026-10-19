/**
 * Hold-to-stop state machine for the recording view.
 *
 * Ensures a take only stops after being held continuously for holdMs (default 2000 ms).
 */

export function createHoldStop({ holdMs = 2000 } = {}) {
  let pressedAt = null;
  let stoppedFired = false;

  return {
    press(t) {
      if (stoppedFired) {
        return { holding: false, progress: 0, stopped: false };
      }
      if (pressedAt === null) {
        pressedAt = t;
      }
      return { holding: true, progress: 0, stopped: false };
    },

    release(_t) {
      if (stoppedFired) {
        return { holding: false, progress: 0, stopped: false };
      }
      pressedAt = null;
      return { stopped: false, holding: false, progress: 0 };
    },

    tick(t) {
      if (stoppedFired || pressedAt === null) {
        return { holding: false, progress: 0, stopped: false };
      }

      const elapsed = t - pressedAt;
      if (elapsed < 0) {
        return { holding: true, progress: 0, stopped: false };
      }

      const progress = Math.min(1, Math.max(0, elapsed / holdMs));
      if (elapsed >= holdMs) {
        stoppedFired = true;
        pressedAt = null;
        return { holding: true, progress: 1, stopped: true };
      }

      return { holding: true, progress, stopped: false };
    },

    reset() {
      pressedAt = null;
      stoppedFired = false;
    },
  };
}
