// Slow hold-to-play listening (WP26): Shift+J plays backward and Shift+L forward at a slow
// tape speed (pitch follows the speed) only while the key is held. A pure state machine; the
// app wires keydown/keyup/blur/commands to it and the transport to start and stop.
// Mirrors src/kuulas/shuttle.py (SLOW_SPEEDS, slow_hold_speed).

export const SLOW_SPEEDS = [0.25, 0.5, 0.75];
export const DEFAULT_SLOW = 0.5;

/** A stored or typed value -> one of SLOW_SPEEDS, else the default. */
export function normaliseSlow(value) {
  const n = Number(value);
  return value !== null && value !== undefined && SLOW_SPEEDS.includes(n) ? n : DEFAULT_SLOW;
}

/** Signed speed for "l" (forward) or "j" (backward). */
export function slowSpeed(direction, setting = DEFAULT_SLOW) {
  const speed = SLOW_SPEEDS.includes(setting) ? setting : DEFAULT_SLOW;
  if (direction === "l") return speed;
  if (direction === "j") return -speed;
  throw new Error(`unknown slow direction: ${direction}`);
}

/**
 * `canStart()` is false while normal playback runs: the press is then ignored (it never
 * disturbs a run). `start(direction)` and `stop()` do the playing.
 */
export function createSlowHold({ canStart, start, stop }) {
  let held = null; // { direction, code }
  return {
    isHeld: () => held !== null,
    /** A keydown (auto-repeats included). `code` is the physical key. */
    press(direction, code) {
      if (held !== null || !canStart()) return;
      held = { direction, code };
      start(direction);
    },
    /** A keyup: the held key itself, or Shift, ends it. */
    release(code) {
      if (held === null) return;
      if (code !== held.code && !code.startsWith("Shift")) return;
      this.cancel();
    },
    /** Window blur, focus loss, Esc or any other transport command. */
    cancel() {
      if (held === null) return;
      held = null;
      stop();
    },
  };
}
