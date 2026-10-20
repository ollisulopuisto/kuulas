// The backing size of a canvas: its CSS size times the device pixel ratio, capped
// at MAX_CANVAS_PIXELS. Each canvas costs 4 bytes per backing pixel in the
// browser and again in the window server's surfaces; a full-screen timeline on a
// 5K display at ratio 2 is 14.7 Mpx = 59 MB per layer. The cap lowers the ratio
// (slightly softer lines) instead of letting a huge window or a high zoom of the
// page multiply that. Canvases are sized to the viewport, never to the timeline.

/** At most this many backing pixels per canvas (32 MB at 4 bytes each). */
export const MAX_CANVAS_PIXELS = 8 * 1024 * 1024;

/**
 * { width, height, ratio } of the backing store for a canvas `cssWidth` x
 * `cssHeight` CSS pixels at `ratio` (devicePixelRatio). The ratio is lowered, never
 * below 1, until the pixel count fits; at ratio 1 a canvas bigger than the cap is
 * scaled down too (ratio below 1), so the cap always holds.
 */
export function backingSize(cssWidth, cssHeight, ratio = 1, maxPixels = MAX_CANVAS_PIXELS) {
  const w = Math.max(0, Math.round(cssWidth));
  const h = Math.max(0, Math.round(cssHeight));
  let r = Number.isFinite(ratio) && ratio > 0 ? ratio : 1;
  if (w * h * r * r > maxPixels) {
    r = Math.sqrt(maxPixels / Math.max(1, w * h));
  }
  let width = Math.floor(w * r);
  let height = Math.floor(h * r);
  while (width * height > maxPixels) {
    width = Math.max(0, width - 1);
    height = Math.max(0, height - 1);
  }
  return { width, height, ratio: r };
}
