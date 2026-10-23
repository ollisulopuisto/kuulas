// Snapping to the volume automation while a modifier is held during a clip move (owner,
// 2026-10-23): the frames where the level really changes, not every point. A track's automation
// points (the automixer's ducking, or drawn by hand) and the envelope points of other clips are
// borders where the level changes by a few dB: the ends of a ramp. The edges of the stretches
// Auto-Silence closed are borders too. Pure; timeline.js adds them to the snap targets while the
// modifier is down and draws them as small marks.

/** A level change of at least this many dB makes a point a border (its neighbour differs). */
export const SIGNIFICANT_DB = 3;

/** The frames of the points of a sorted [frame, dB] list that start or end a real change. */
function significant(points, toFrame) {
  const out = [];
  for (let i = 0; i < points.length; i += 1) {
    const [, db] = points[i];
    const before = i > 0 ? Math.abs(db - points[i - 1][1]) : 0;
    const after = i < points.length - 1 ? Math.abs(points[i + 1][1] - db) : 0;
    if (before >= SIGNIFICANT_DB || after >= SIGNIFICANT_DB) out.push(toFrame(points[i][0]));
  }
  return out;
}

/**
 * The frames to snap to while the modifier is held: significant track automation points, the
 * edges of closed stretches, and the significant envelope points of clips that are not being
 * moved (`movedIds`), at their place on the timeline. Sorted, unique.
 */
export function automationTargets(project, movedIds) {
  const skip = new Set(movedIds ?? []);
  const frames = new Set();
  for (const track of project?.tracks ?? []) {
    const automation = [...(track.automation ?? [])].sort((a, b) => a[0] - b[0]);
    for (const frame of significant(automation, (f) => f)) frames.add(frame);
    for (const [start, end] of track.gate ?? []) {
      frames.add(start);
      frames.add(end);
    }
    for (const clip of track.clips ?? []) {
      if (skip.has(clip.id) || !clip.envelope?.length) continue;
      const envelope = [...clip.envelope].sort((a, b) => a[0] - b[0]);
      for (const frame of significant(envelope, (f) => clip.start + (f - (clip.offset ?? 0)))) {
        frames.add(frame);
      }
    }
  }
  return [...frames].sort((a, b) => a - b);
}
