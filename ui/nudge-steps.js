/**
 * Nudge step sizes and frame conversions.
 */

export const NUDGE_STEPS_MS = [1, 10, 100, 1000];

export function nudgeFrames(stepMs, rate) {
  if (
    typeof stepMs !== "number" ||
    typeof rate !== "number" ||
    !Number.isFinite(stepMs) ||
    !Number.isFinite(rate) ||
    stepMs <= 0 ||
    rate <= 0
  ) {
    return 0;
  }
  return Math.max(1, Math.round((stepMs * rate) / 1000));
}

export function nextStep(stepMs, direction) {
  let bestIdx = 0;
  let bestDiff = Math.abs(NUDGE_STEPS_MS[0] - stepMs);

  for (let i = 1; i < NUDGE_STEPS_MS.length; i++) {
    const diff = Math.abs(NUDGE_STEPS_MS[i] - stepMs);
    // Strict inequality (<) ensures ties go to the smaller value (earlier index)
    if (diff < bestDiff) {
      bestDiff = diff;
      bestIdx = i;
    }
  }

  if (direction > 0) {
    const targetIdx = Math.min(NUDGE_STEPS_MS.length - 1, bestIdx + 1);
    return NUDGE_STEPS_MS[targetIdx];
  }
  if (direction < 0) {
    const targetIdx = Math.max(0, bestIdx - 1);
    return NUDGE_STEPS_MS[targetIdx];
  }
  return NUDGE_STEPS_MS[bestIdx];
}
