// Following the playhead while playing: page or continuous. `paused` is "Follow is off"
// (follow-model.js owns when it changes); it never clears here, not even when the playhead is
// back in view by the user's own scrolling.
const PAGE_MARGIN = 0.1;

/** The scroll that shows `playhead` with the page margin before it. */
export function scrollFor(playhead, zoom, width) {
  return Math.max(0, Math.round(playhead - PAGE_MARGIN * width * zoom));
}

/**
 * Returns { scroll, paused }. `paused` is passed through unchanged.
 * `moved`: the playhead changed in this update (a jump).
 */
export function followScroll({
  mode,
  paused,
  playing,
  playhead,
  scroll,
  zoom,
  width,
  moved = false,
}) {
  const visible = width * zoom;
  const inView = playhead >= scroll && playhead < scroll + visible;
  if (!playing) {
    // A jump while stopped (Home, End, Tab, a marker) shows where the playhead went;
    // scrolling by hand does not move the playhead, so it is left alone.
    if (moved && !inView && !paused) {
      return { scroll: Math.max(0, Math.round(playhead - PAGE_MARGIN * visible)), paused };
    }
    return { scroll, paused };
  }
  if (paused) return { scroll, paused };
  if (mode === "continuous") {
    return { scroll: Math.max(0, Math.round(playhead - visible / 2)), paused: false };
  }
  if (inView) return { scroll, paused: false };
  return { scroll: Math.max(0, Math.round(playhead - PAGE_MARGIN * visible)), paused: false };
}
