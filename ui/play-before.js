// Jump back and play (P) preference: how many seconds before the playhead it starts playing.

export const PLAY_BEFORE_KEY = "playBeforeS";
export const MIN_PLAY_BEFORE_S = 0.5;
export const MAX_PLAY_BEFORE_S = 10;
export const PLAY_BEFORE_STEP_S = 0.5;
export const DEFAULT_PLAY_BEFORE_S = 3;

/** Normalise any stored or typed value to a finite number in [0.5, 10] s, rounded to 0.5 s steps. */
export function normalisePlayBefore(value) {
  if (value === null || value === undefined || value === "") return DEFAULT_PLAY_BEFORE_S;
  const n = Number(value);
  if (!Number.isFinite(n)) return DEFAULT_PLAY_BEFORE_S;
  const clamped = Math.min(MAX_PLAY_BEFORE_S, Math.max(MIN_PLAY_BEFORE_S, n));
  return Math.round(Math.round(clamped / PLAY_BEFORE_STEP_S) * PLAY_BEFORE_STEP_S * 10) / 10;
}
