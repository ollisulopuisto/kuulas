// Auto-Silence ranges are in absolute source frames; this view maps them through one clip.
import { gateAt } from "./gate.js";

export function implicitSilenceRanges(clip) {
  const sourceStart = clip.offset ?? 0;
  const sourceEnd = sourceStart + clip.length;
  const out = [];
  for (const [from, to] of clip.auto_silence ?? []) {
    const start = Math.max(from, sourceStart);
    const end = Math.min(to, sourceEnd);
    if (end > start) out.push([clip.start + start - sourceStart, clip.start + end - sourceStart]);
  }
  return out;
}

export function implicitSilenceAt(project, trackId, frame, zoom = 1) {
  const track = project?.tracks?.find((candidate) => candidate.id === trackId);
  for (const clip of track?.clips ?? []) {
    const ranges = implicitSilenceRanges(clip);
    const index = gateAt(ranges, frame, zoom);
    if (index >= 0) {
      return { trackId, clipId: clip.id, index, range: ranges[index], implicit: true };
    }
  }
  return null;
}

/** Alternating audible/closed portions, clipped to this parent. Explicit clips opt out. */
export function implicitPortions(clip, legacyGate = []) {
  if (clip.ungated || clip.muted) return [];
  const spans = [...implicitSilenceRanges(clip), ...legacyGate]
    .map(([a, b]) => [Math.max(clip.start, a), Math.min(clip.start + clip.length, b)])
    .filter(([a, b]) => b > a)
    .sort((a, b) => a[0] - b[0]);
  const closed = [];
  for (const [a, b] of spans) {
    const last = closed.at(-1);
    if (last && a <= last[1]) last[1] = Math.max(last[1], b);
    else closed.push([a, b]);
  }
  if (closed.length === 0) return [];
  const portions = [];
  let start = clip.start;
  for (const [a, b] of closed) {
    if (a > start) portions.push({ range: [start, a], closed: false });
    portions.push({ range: [a, b], closed: true });
    start = b;
  }
  if (start < clip.start + clip.length)
    portions.push({ range: [start, clip.start + clip.length], closed: false });
  return portions;
}

export function implicitPortionAt(clip, frame, legacyGate = []) {
  return (
    implicitPortions(clip, legacyGate).find(({ range: [a, b] }) => a <= frame && frame < b) ?? null
  );
}

export function implicitPortionTarget(project, trackId, frame) {
  const track = project?.tracks?.find((item) => item.id === trackId);
  // Match hitTest's shortest/topmost clip when the cursor is used without a pointer target.
  const clips = (track?.clips ?? [])
    .filter((c) => c.start <= frame && frame < c.start + c.length)
    .sort((a, b) => a.length - b.length);
  const clip = clips[0];
  const portion = clip ? implicitPortionAt(clip, frame, track.gate) : null;
  return portion ? { trackId, clipId: clip.id, implicit: true, ...portion } : null;
}
