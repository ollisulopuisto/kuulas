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

// What a two-finger trackpad scroll does (owner, 2026-10-19): a PREFERENCE with two modes.
//   "zoom" (default): vertical movement zooms time around the pointer, horizontal scrolls time,
//     Shift + vertical scrolls the lanes.
//   "scroll": vertical scrolls the lanes, horizontal scrolls time.
// A notched mouse wheel ignores the preference.
export const WHEEL_MODES = ["zoom", "scroll"];
export const DEFAULT_WHEEL_MODE = "zoom";
export const wheelModeChoice = (stored) =>
  WHEEL_MODES.includes(stored) ? stored : DEFAULT_WHEEL_MODE;
export const nextWheelMode = (mode) => (mode === "zoom" ? "scroll" : "zoom");

/**
 * What a wheel event means:
 *   { kind: "zoom", factor }      Mod + wheel or pinch; factor < 1 zooms in
 *   { kind: "waveform", factor }  Alt + wheel; factor > 1 makes waveforms taller
 *   { kind: "scroll", dx, dy }    pixels to scroll time (dx) and lanes (dy)
 */
export function wheelIntent(event, { lanesFit, mode = DEFAULT_WHEEL_MODE }) {
  const { dx, dy } = pixels(event);
  if (event.ctrlKey || event.metaKey) return { kind: "zoom", factor: Math.exp(dy * 0.01) };
  if (event.altKey) return { kind: "waveform", factor: Math.exp(-(dy || dx) * 0.002) };
  const trackpad = classifyWheel(event) === "trackpad";
  if (event.shiftKey) {
    // Zoom mode: Shift + vertical is how a trackpad reaches the lanes.
    if (trackpad && mode === "zoom" && Math.abs(dy) >= Math.abs(dx))
      return { kind: "scroll", dx: 0, dy };
    return { kind: "scroll", dx: dx || dy, dy: 0 };
  }
  if (trackpad && mode === "zoom") {
    return Math.abs(dy) > Math.abs(dx)
      ? { kind: "zoom", factor: Math.exp(dy * 0.01) }
      : { kind: "scroll", dx, dy: 0 };
  }
  if (trackpad) return { kind: "scroll", dx, dy };
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
