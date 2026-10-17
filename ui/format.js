// Frames, pixels and time. Pure, so `node --test` covers them (ground rule 6:
// the model speaks frames, and conversion happens at the edges only).
import { formatTimecode } from "./i18n.js";

export const RATE = 48_000;

/** "1:02:03,500": a frame as a timecode in the UI language. */
export function frameToTime(frame, rate = RATE) {
  return formatTimecode(frame / rate);
}

/** Pixel column of `frame` when `scroll` is the frame at the left edge. */
export function frameToX(frame, scroll, zoom) {
  return (frame - scroll) / zoom;
}

/** The frame under pixel column `x`, rounded to a whole frame. */
export function xToFrame(x, scroll, zoom) {
  return Math.round(scroll + x * zoom);
}

/** New zoom and scroll that keep the frame under column `x` where it is. */
export function zoomAround({ zoom, scroll, x, nextZoom }) {
  const anchor = scroll + x * zoom;
  return { zoom: nextZoom, scroll: Math.max(0, Math.round(anchor - x * nextZoom)) };
}
