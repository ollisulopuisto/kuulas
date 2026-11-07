import { frameToX } from "./format.js";
import { RULER_HEIGHT, visibleRows } from "./lanes.js";

/** Pixel boxes for the historical clips intersecting the current timeline viewport. */
export function historyPreviewBoxes(clips, { layout, view }) {
  if (!Array.isArray(clips) || !layout || !view) return [];
  const { scroll, zoom, scrollY = 0, width, height } = view;
  if (![scroll, zoom, scrollY, width, height].every(Number.isFinite) || zoom <= 0) return [];

  const rowByTrack = new Map(
    visibleRows(layout, scrollY, Math.max(0, height - RULER_HEIGHT))
      .filter((row) => row.kind === "track")
      .map((row) => [row.id, row]),
  );
  const firstFrame = scroll;
  const lastFrame = scroll + width * zoom;
  const boxes = [];

  for (const clip of clips) {
    const row = rowByTrack.get(clip?.track);
    if (
      !row ||
      typeof clip.clip !== "string" ||
      !Number.isFinite(clip.start) ||
      !Number.isFinite(clip.end)
    )
      continue;
    if (clip.end <= clip.start || clip.end <= firstFrame || clip.start >= lastFrame) continue;

    const left = Math.max(firstFrame, clip.start);
    const right = Math.min(lastFrame, clip.end);
    const rowTop = RULER_HEIGHT + row.top - scrollY;
    const top = Math.max(RULER_HEIGHT, rowTop + 2);
    const bottom = Math.min(height, rowTop + row.height - 2);
    if (bottom <= top) continue;
    const x = frameToX(left, scroll, zoom);
    boxes.push({
      clipId: clip.clip,
      trackId: clip.track,
      x,
      y: top,
      w: Math.max(0, frameToX(right, scroll, zoom) - x),
      h: bottom - top,
    });
  }
  return boxes;
}

/** Draw non-interactive, dashed outlines for the calculated historical clip boxes. */
export function drawHistoryPreview(context, boxes, colour) {
  if (!context || !Array.isArray(boxes) || boxes.length === 0) return;
  context.save();
  context.strokeStyle = colour;
  context.lineWidth = 1.5;
  context.setLineDash([5, 4]);
  for (const box of boxes) {
    context.strokeRect(box.x + 0.5, box.y + 0.5, Math.max(0, box.w - 1), Math.max(0, box.h - 1));
  }
  context.setLineDash([]);
  context.restore();
}
