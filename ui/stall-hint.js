/**
 * Detects whether a long-running job appears stuck or is making progress.
 *
 * Samples track (t, progress, message). Progress or message changes count as activity.
 */

function lastChange(samples) {
  const last = samples[samples.length - 1];
  for (let i = samples.length - 2; i >= 0; i--) {
    if (samples[i].progress !== last.progress || samples[i].message !== last.message) {
      return samples[i + 1].t;
    }
  }
  return samples[0].t;
}

export function stallState(samples, now, { quietMs = 15000, stuckMs = 90000 } = {}) {
  if (!samples || samples.length === 0) {
    return "moving";
  }

  const lastSample = samples[samples.length - 1];
  if (now < lastSample.t) {
    throw new Error("now cannot be before the last sample");
  }

  const elapsed = now - lastChange(samples);
  if (elapsed >= stuckMs) {
    return "stuck";
  }
  if (elapsed >= quietMs) {
    return "quiet";
  }
  return "moving";
}

export function quietSeconds(samples, now, { quietMs = 15000, stuckMs = 90000 } = {}) {
  if (!samples || samples.length === 0) {
    return 0;
  }

  const state = stallState(samples, now, { quietMs, stuckMs });
  if (state === "moving") {
    return 0;
  }

  const elapsed = now - lastChange(samples);
  return Math.floor(elapsed / 1000);
}
