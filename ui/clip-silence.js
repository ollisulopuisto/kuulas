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
