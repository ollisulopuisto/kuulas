// Following the playhead while playing: page or continuous. Scrolling by hand
// pauses it until the follow key is pressed or the playhead is back in view.
const PAGE_MARGIN = 0.1;

/**
 * Returns { scroll, paused }. `paused` is true while the user has scrolled away
 * and the playhead is off screen; it clears by itself once the playhead is back.
 */
export function followScroll({ mode, paused, playing, playhead, scroll, zoom, width }) {
  if (!playing) return { scroll, paused };
  const visible = width * zoom;
  const inView = playhead >= scroll && playhead < scroll + visible;
  if (paused) return { scroll, paused: !inView };
  if (mode === "continuous") {
    return { scroll: Math.max(0, Math.round(playhead - visible / 2)), paused: false };
  }
  if (inView) return { scroll, paused: false };
  return { scroll: Math.max(0, Math.round(playhead - PAGE_MARGIN * visible)), paused: false };
}
