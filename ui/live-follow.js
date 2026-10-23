// The view following the take's head while it records (owner, 2026-10-23: "like Follow with
// the playhead"). While you are watching the head it pages forward when the head runs off the
// right edge; once you scroll or zoom so that the head is not in view, it leaves the view alone
// until the head is back in view by itself. Pure; app.js keeps `wasInView` between level events.
import { scrollFor } from "./follow.js";

/** Whether `head` is inside the visible stretch. */
export function headInView({ head, scroll, zoom, width }) {
  return head >= scroll && head < scroll + width * zoom;
}

/** The scroll to page to, or null to leave the view alone. */
export function liveFollowScroll({ head, scroll, zoom, width, wasInView }) {
  if (!wasInView || headInView({ head, scroll, zoom, width })) return null;
  if (head < scroll) return null; // you scrolled to the right of it
  return scrollFor(head, zoom, width);
}
