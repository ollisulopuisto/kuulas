// Fast listening: a port of src/kuulas/fast_speed.py. A toggle between normal speed and a
// chosen speed; the chosen speed is stepless from 1.0x to 2.0x (owner, 2026-10-18), nudged by
// 0.05x or set from the slider. Both read ui/tests/fixtures/fast-speed-cases.json, so they
// cannot drift apart.

export const MIN_FAST = 1;
export const MAX_FAST = 2;
/** One key press or slider tick. */
export const STEP = 0.05;
/** What the toggle turns on when the chosen speed is 1.0 (it would do nothing). */
export const DEFAULT_FAST = 1.5;

export const NORMAL = { fast: DEFAULT_FAST, active: false };

/** The nearest multiple of STEP, as a number with no float dust (1.35, not 1.3500000000000001). */
const snap = (speed) => Math.round(Math.round(speed / STEP) * STEP * 100) / 100;
const clamp = (speed) => Math.max(MIN_FAST, Math.min(MAX_FAST, snap(speed)));

/** The speed to play at: 1 when off, the chosen speed when on. */
export const effective = (state) => (state.active ? state.fast : 1);

export function toggle(state) {
  if (state.active) return { ...state, active: false };
  return { fast: state.fast > MIN_FAST ? state.fast : DEFAULT_FAST, active: true };
}
export const stepUp = (state) => ({ ...state, fast: clamp(state.fast + STEP) });
export const stepDown = (state) => ({ ...state, fast: clamp(state.fast - STEP) });
export const setFast = (state, value) => ({ ...state, fast: clamp(value) });
/** Pixels of a horizontal drag on the speed display for one step (120 px cover 1.0 to 2.0). */
export const PX_PER_STEP = 6;
/** The speed after dragging the display `dx` pixels from `start`: right is faster. */
export const dragSpeed = (start, dx) => clamp(start + (dx / PX_PER_STEP) * STEP);
/** Back to normal: chosen speed 1.0 and off. */
export const reset = () => ({ fast: MIN_FAST, active: false });

/** What is remembered: the stored JSON, any garbage -> the default. */
export function fromStored(value) {
  if (!value || typeof value !== "object") return { ...NORMAL };
  const fast = Number(value.fast);
  if (!Number.isFinite(fast)) return { ...NORMAL };
  return { fast: clamp(fast), active: value.active === true };
}

/**
 * The chip's number ("1.35", "1,35" through `format`, the UI's number formatter), or null
 * when fast listening is off or the chosen speed is 1.0.
 */
export function chipFast(state, format) {
  const speed = effective(state);
  if (speed === 1) return null;
  const hundredths = Math.round(speed * 100);
  const digits = hundredths % 100 === 0 ? 0 : hundredths % 10 === 0 ? 1 : 2;
  return format(speed, { digits });
}
