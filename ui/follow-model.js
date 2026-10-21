// Follow is a state, not an action (owner, 2026-10-21). While it is on, the view follows the
// playhead (follow.js does the scrolling). A view operation by the user detaches it; only the
// events below put it back. Nothing implicit: not a timer, not the playhead coming into view by
// the user's own scrolling, not a click near the playhead's time.

/** The playhead handle's hit area, either side, in px (owner: about 6). */
export const HANDLE_PX = 6;

/**
 * One event -> { follow, shouldScroll }. `shouldScroll`: scroll the view to the playhead now.
 * Events: view-op {playing}, play-start, play-stop, jump {inView} (Home/End, marker, go to time),
 * handle (a click on the playhead handle), show {inView} (chip, arrow, menu), toggle {inView},
 * seek {inView} (a click or seek that is not a transport jump). Any other event changes nothing.
 */
export function followStep({ follow }, event) {
  const keep = { follow, shouldScroll: false };
  switch (event.type) {
    case "view-op":
      // Stopped, there is nothing to follow; the next start resets it anyway.
      return event.playing ? { follow: false, shouldScroll: false } : keep;
    case "play-start":
    case "play-stop":
    case "handle":
      return { follow: true, shouldScroll: false };
    case "jump":
    case "show":
      return { follow: true, shouldScroll: !event.inView };
    case "toggle":
      return follow
        ? { follow: false, shouldScroll: false }
        : followStep({ follow }, { ...event, type: "show" });
    case "seek":
      // The user asked to go there: once, and only while following.
      return { follow, shouldScroll: follow && !event.inView };
    default:
      return keep;
  }
}

/** True when a click at `frame` is on the playhead's handle or line. */
export function onHandle({ playhead, frame, zoom }) {
  return Math.abs(frame - playhead) <= HANDLE_PX * zoom;
}

/** "left" / "right": the edge arrow, only with follow off and the playhead out of the view. */
export function arrowOf({ follow, playhead, scroll, zoom, width }) {
  if (follow) return null;
  if (playhead < scroll) return "left";
  if (playhead >= scroll + width * zoom) return "right";
  return null;
}

/** Whether the playhead is inside the visible stretch. */
export function inView({ playhead, scroll, zoom, width }) {
  return playhead >= scroll && playhead < scroll + width * zoom;
}
