import { formatTimecode } from "./i18n.js";

export const RATE = 48_000;

export function frameToTime(frame, _language) {
  return formatTimecode(frame / RATE);
}

export function frameToX(frame, scroll, zoom) {
  return (frame - scroll) / zoom;
}

export function timeToFrame(x, scroll, zoom) {
  return Math.round(scroll + x * zoom);
}

export function zoomAround({ zoom, scroll, x, nextZoom }) {
  const anchor = scroll + x * zoom;
  return { zoom: nextZoom, scroll: Math.max(0, Math.round(anchor - x * nextZoom)) };
}

export function hitTestLane(y, scrollY, tracks, laneHeight) {
  const index = Math.floor((y + scrollY) / laneHeight);
  return tracks[index]?.id ?? null;
}

export function hitTestClip(frame, trackId, clips) {
  return clips.find((clip) => clip.track === trackId && frame >= clip.start && frame < clip.end)?.id ?? null;
}

export function waveformColumns(peaks, mode = "half", scale = "linear", height = 48) {
  return Array.from(peaks, ([minimum, maximum]) => {
    const magnitude = Math.max(Math.abs(minimum), Math.abs(maximum));
    const level = scale === "db" ? Math.max(0, (20 * Math.log10(Math.max(magnitude, 10 ** (-48 / 20)) ) + 48) / 48) : magnitude;
    return { magnitude, height: Math.max(1, level * height), minimum, maximum, mode };
  });
}
