// Loudness tint against a target. Pure: no DOM, no imports.
export function loudnessState(lufs, target) {
  if (lufs == null || target == null) return "none";
  if (!Number.isFinite(lufs) || !Number.isFinite(target)) return "none";
  const d = Math.abs(lufs - target);
  if (d <= 2) return "ok";
  if (d <= 5) return "notice";
  return "warn";
}

export function curveRuns(points, target) {
  const runs = [];
  for (const [time, lufs] of points) {
    const state = loudnessState(lufs, target);
    const last = runs[runs.length - 1];
    if (last && last.state === state) {
      last.end = time;
    } else {
      runs.push({ start: time, end: time, state });
    }
  }
  return runs;
}
