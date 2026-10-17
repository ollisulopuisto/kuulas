// Wheel and trackpad intent. Pure: the DOM handler passes the event's fields.
const LINE_PX = 16;
const PAGE_PX = 400;
// A notched wheel reports whole multiples of ~100 px (Chrome, Windows) or
// lines (Firefox); a trackpad reports small, often fractional, two-axis deltas.
const NOTCH_MIN = 50;

export function classifyWheel(event) {
  if (event.deltaMode !== 0) return "mouse";
  const whole = Number.isInteger(event.deltaY) && Number.isInteger(event.deltaX);
  return whole && event.deltaX === 0 && Math.abs(event.deltaY) >= NOTCH_MIN ? "mouse" : "trackpad";
}

function pixels(event) {
  const unit = event.deltaMode === 1 ? LINE_PX : event.deltaMode === 2 ? PAGE_PX : 1;
  return { dx: event.deltaX * unit, dy: event.deltaY * unit };
}

/**
 * What a wheel event means:
 *   { kind: "zoom", factor }      Mod + wheel or pinch; factor < 1 zooms in
 *   { kind: "waveform", factor }  Alt + wheel; factor > 1 makes waveforms taller
 *   { kind: "scroll", dx, dy }    pixels to scroll time (dx) and lanes (dy)
 */
export function wheelIntent(event, { lanesFit }) {
  const { dx, dy } = pixels(event);
  if (event.ctrlKey || event.metaKey) return { kind: "zoom", factor: Math.exp(dy * 0.01) };
  if (event.altKey) return { kind: "waveform", factor: Math.exp(-(dy || dx) * 0.002) };
  if (event.shiftKey) return { kind: "scroll", dx: dx || dy, dy: 0 };
  if (classifyWheel(event) === "trackpad") return { kind: "scroll", dx, dy };
  return lanesFit ? { kind: "scroll", dx: dx || dy, dy: 0 } : { kind: "scroll", dx: 0, dy };
}

/**
 * What a Safari pinch gesture means:
 *   { kind: "zoom", factor }   factor < 1 zooms in (spreading fingers)
 *   null                       scale missing, 0, or non-finite
 */
export function gestureZoom(previousScale, scale) {
  if (!Number.isFinite(previousScale) || !Number.isFinite(scale) || scale === 0) return null;
  return { kind: "zoom", factor: previousScale / scale };
}
