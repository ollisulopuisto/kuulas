// The waveform inside a dragged clip's ghost (WP63 part 1). Pure, no DOM. The columns are
// built once per drag (and again only when the zoom changes, more tiles arrive or the view
// slides past the built window); moving the pointer only translates them.
import { gained } from "./paint.js";
import { columnsFromTiles, pickLevel } from "./waveform.js";

/** Alpha of the ghost waveform: about half see-through, so the lane below still reads. */
export const GHOST_ALPHA = 0.55;
/** A muted clip's ghost waveform is this fraction of that, like the lane's muted dimming. */
export const GHOST_MUTED_FACTOR = 0.6;

/**
 * The ghost's peak columns, one per pixel, as the lane would draw them: min/max pairs with the
 * clip gain (and envelope) applied. `lookup(tileIndex)` returns a tile or undefined.
 * `first`/`count` select a window of columns (0 = the clip's first), so a long clip at high
 * zoom never builds millions of columns. Returns { data, missing, level, first }; `missing`
 * lists tiles still to fetch, whose columns stay 0,0 until they arrive.
 */
export function ghostColumns({
  lookup,
  offset,
  length,
  zoom,
  gainDb = 0,
  envelope = null,
  first = 0,
  count,
}) {
  const total = Math.max(0, Math.ceil(length / zoom));
  const start = Math.max(0, Math.min(first, total));
  const n = Math.max(0, Math.min(count ?? total - start, total - start));
  const level = pickLevel(zoom);
  const startFrame = offset + start * zoom;
  const { data, missing } = columnsFromTiles({
    lookup,
    level,
    startFrame,
    framesPerPixel: zoom,
    count: n,
  });
  const clip = { gainDb, envelope: envelope?.length ? envelope : null };
  return { data: gained(clip, data, startFrame, zoom).shown, missing, level, first: start };
}

/**
 * Which of a ghost's columns are on screen: ghost left edge `x` (canvas px), width `w`, canvas
 * `width`, plus `margin` columns each side so small pointer moves need no rebuild. Null when
 * the ghost is entirely off screen.
 */
export function ghostWindow(x, w, width, margin = 0) {
  const left = Math.round(x);
  if (left >= width || left + w <= 0) return null;
  const first = Math.max(0, -left - margin);
  const last = Math.min(w, width - left + margin);
  return { first, count: Math.max(0, last - first) };
}

/** True when the built window `have` ({first, count}) still covers what is visible, `need`. */
export function windowCovers(have, need) {
  return Boolean(
    have && need && have.first <= need.first && have.first + have.count >= need.first + need.count,
  );
}
