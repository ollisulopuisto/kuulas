/** The loop range to preview, in priority order: marks, selection, clip. */
export function loopRange({ inPoint, outPoint, selection, clip }) {
  if (typeof inPoint === "number" && typeof outPoint === "number" && outPoint > inPoint) {
    return { start: inPoint, end: outPoint, source: "marks" };
  }
  if (
    selection &&
    typeof selection.start === "number" &&
    typeof selection.end === "number" &&
    selection.end > selection.start
  ) {
    return { start: selection.start, end: selection.end, source: "selection" };
  }
  if (
    clip &&
    typeof clip.start === "number" &&
    typeof clip.length === "number" &&
    clip.length > 0
  ) {
    return { start: clip.start, end: clip.start + clip.length, source: "clip" };
  }
  return null;
}

/** Widen a loop range by `seconds` on each side for the candidate preview. */
export function previewLoop(range, { rate, total, seconds = 2 }) {
  if (!range) return null;
  const pad = Math.round(seconds * rate);
  const start = Math.max(0, range.start - pad);
  const end = Math.min(total, range.end + pad);
  return { start, end };
}
