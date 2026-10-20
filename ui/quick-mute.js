// Quick mute (owner, 2026-10-20, "form 2"): one key mutes a short fixed stretch centred on the
// play cursor, to take out a lip smack while listening. The stretch is a setting in Preferences
// (seconds, 0.1-2.0, default 0.5). Pure helpers; the edit itself is `quickMutePlan`
// (edit-plans.js), which sends one `mute_range` (a soft cut, nothing is deleted).

export const QUICK_MUTE_KEY = "quickMuteS";
export const MIN_QUICK_MUTE_S = 0.1;
export const MAX_QUICK_MUTE_S = 2.0;
export const QUICK_MUTE_STEP_S = 0.05;
export const DEFAULT_QUICK_MUTE_S = 0.5;

/** A stored or typed value -> seconds within the bounds (on the step), else the default. */
export function normaliseQuickMute(value) {
  if (value === null || value === undefined || value === "") return DEFAULT_QUICK_MUTE_S;
  const n = Number(value);
  if (!Number.isFinite(n)) return DEFAULT_QUICK_MUTE_S;
  const clamped = Math.min(MAX_QUICK_MUTE_S, Math.max(MIN_QUICK_MUTE_S, n));
  return Math.round(Math.round(clamped / QUICK_MUTE_STEP_S) * QUICK_MUTE_STEP_S * 1000) / 1000;
}

/**
 * The frames to mute: half the setting before `playhead`, half after, never before frame 0.
 * Clipping to the clips is the plan's job (and `ops.mute_ranges` splits only inside clips).
 */
export function quickMuteStretch(playhead, rate, seconds) {
  const half = Math.round((normaliseQuickMute(seconds) * rate) / 2);
  const at = Math.round(playhead);
  return { start: Math.max(0, at - half), end: at + half };
}
