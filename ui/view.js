// The time axis: zoom levels, anchors, the Z close/wide toggle, view history
// and the overview strip. Pure functions on plain values; app.js applies the
// results to the store and the canvas. `zoom` is frames per pixel and `scroll`
// the frame at the left edge, both UI state that never enters the edit history.
import { projectEnd } from "./lanes.js";

/** Seconds on screen of the snap levels between "whole edit" and "samples". */
export const SNAP_SECONDS = [1800, 600, 300, 120, 60, 30, 10, 5, 2, 1, 0.5, 0.1];
/** Eight pixels per frame: single samples are distinct enough to edit. */
export const SAMPLE_ZOOM = 1 / 8;
/** A continuous zoom released this close to a level settles on it. */
export const SNAP_TOLERANCE = 0.08;
/** Two zooms this close are "the same level" (float noise, not a choice). */
const SAME = 0.005;
const DEFAULT_CLOSE_SECONDS = 2;
const EMPTY_EDIT_SECONDS = 30;
const HISTORY_LIMIT = 50;

const same = (a, b) => Math.abs(a / b - 1) < SAME;

/**
 * The snap levels, widest first: the whole edit, then every time level that is
 * narrower than the whole edit, then samples. A level is a zoom (frames per
 * pixel) that puts that much time across `width` pixels.
 */
export function zoomLevels({ width, rate, totalFrames }) {
  const span = totalFrames > 0 ? totalFrames : EMPTY_EDIT_SECONDS * rate;
  const whole = span / width;
  const levels = [{ kind: "whole", seconds: span / rate, zoom: whole }];
  for (const seconds of SNAP_SECONDS) {
    const zoom = (seconds * rate) / width;
    if (zoom < whole && !same(zoom, whole)) levels.push({ kind: "time", seconds, zoom });
  }
  const samples = { kind: "samples", seconds: (SAMPLE_ZOOM * width) / rate, zoom: SAMPLE_ZOOM };
  if (samples.zoom < levels.at(-1).zoom) levels.push(samples);
  return levels;
}

/** The level `zoom` is within the snap tolerance of, else `zoom` itself. */
export function snapZoom(zoom, levels, tolerance = SNAP_TOLERANCE) {
  let best = null;
  for (const level of levels) {
    const ratio = Math.max(zoom / level.zoom, level.zoom / zoom);
    if (ratio <= 1 + tolerance && (!best || ratio < best.ratio)) best = { ratio, zoom: level.zoom };
  }
  return best ? best.zoom : zoom;
}

/** The next level closer (direction +1) or wider (-1); stays at either end. */
export function stepZoom(zoom, levels, direction) {
  if (direction > 0) {
    const closer = levels.find((level) => level.zoom < zoom && !same(level.zoom, zoom));
    return closer ? closer.zoom : levels.at(-1).zoom <= zoom ? levels.at(-1).zoom : zoom;
  }
  for (let i = levels.length - 1; i >= 0; i -= 1) {
    if (levels[i].zoom > zoom && !same(levels[i].zoom, zoom)) return levels[i].zoom;
  }
  return levels[0].zoom >= zoom ? levels[0].zoom : zoom;
}

/** { kind, seconds }: "whole", "samples", or a time on screen (snapped or free). */
export function describeZoom(zoom, levels, { width, rate }) {
  const level = levels.find((candidate) => same(candidate.zoom, zoom));
  if (level?.kind === "whole") return { kind: "whole", seconds: level.seconds };
  if (level?.kind === "samples") return { kind: "samples", seconds: level.seconds };
  return { kind: "time", seconds: (zoom * width) / rate };
}

/** A time span as a number and a unit for display: 30 min, 2 s, 500 ms. */
export function spanParts(seconds) {
  if (seconds >= 60) return { unit: "min", value: round1(seconds / 60) };
  if (seconds >= 1) return { unit: "s", value: round1(seconds) };
  return { unit: "ms", value: Math.round(seconds * 1000) };
}

const round1 = (value) => Math.round(value * 10) / 10;

/** Scroll limits: never before the start; half a screen of room after the end. */
export function clampScroll(scroll, zoom, width, totalFrames) {
  const visible = width * zoom;
  const max = visible >= totalFrames ? 0 : totalFrames - visible / 2;
  return Math.max(0, Math.min(scroll, max));
}

/** Zoom to `nextZoom` with the frame `anchorFrame` staying at the same x. */
export function zoomAt({ zoom, scroll }, anchorFrame, nextZoom, bounds = null) {
  const x = (anchorFrame - scroll) / zoom;
  let next = anchorFrame - x * nextZoom;
  next = bounds ? clampScroll(next, nextZoom, bounds.width, bounds.totalFrames) : Math.max(0, next);
  return { zoom: nextZoom, scroll: Math.round(next) };
}

/** Which frame a zoom keeps still: last edit, else the pointer, else the playhead. */
export function pickAnchor({ lastEdit, pointerFrame, playhead }) {
  if (lastEdit !== null && lastEdit !== undefined) return { frame: lastEdit, source: "edit" };
  if (pointerFrame !== null && pointerFrame !== undefined) {
    return { frame: pointerFrame, source: "pointer" };
  }
  return { frame: playhead, source: "playhead" };
}

// -- Z: a close view and a wide view -------------------------------------------

export const initialViews = () => ({
  current: "wide",
  close: { zoom: null },
  wide: { zoom: null, scroll: 0 },
});

/** Record the live view in whichever slot is current (= - and Shift+Z do this). */
export function rememberView(views, now) {
  if (views.current === "close") return { ...views, close: { zoom: now.zoom } };
  return { ...views, wide: { zoom: now.zoom, scroll: now.scroll } };
}

/**
 * Z: save where we are in the current slot, then go to the other one. The close
 * view remembers its level only and opens around the anchor, which stays where
 * it is on screen (centred if it was off screen); the wide view also remembers
 * its position. A slot never used is 2 s on screen (close) or the whole edit.
 */
export function toggleView(views, now, { anchorFrame, width, levels, totalFrames }) {
  const saved = rememberView(views, now);
  if (views.current === "wide") {
    const defaultClose = levels.find((l) => l.seconds === DEFAULT_CLOSE_SECONDS) ?? levels[0];
    const zoom = saved.close.zoom ?? defaultClose.zoom;
    const x = (anchorFrame - now.scroll) / now.zoom;
    const onScreen = x >= 0 && x <= width;
    const scroll = anchorFrame - (onScreen ? x : width / 2) * zoom;
    return {
      views: { ...saved, current: "close" },
      zoom,
      scroll: Math.round(clampScroll(scroll, zoom, width, totalFrames)),
    };
  }
  const zoom = saved.wide.zoom ?? levels[0].zoom;
  return {
    views: { ...saved, current: "wide" },
    zoom,
    scroll: Math.round(clampScroll(saved.wide.scroll, zoom, width, totalFrames)),
  };
}

// -- view history (Alt+Z), never the undo history --------------------------------

export const createViewHistory = (limit = HISTORY_LIMIT) => ({ entries: [], cursor: -1, limit });

/** A new view reached by a deliberate change; drops the views ahead of the cursor. */
export function visitView(history, view) {
  const current = history.entries[history.cursor];
  if (current && current.zoom === view.zoom && current.scroll === view.scroll) return history;
  let entries = [
    ...history.entries.slice(0, history.cursor + 1),
    { zoom: view.zoom, scroll: view.scroll },
  ];
  if (entries.length > history.limit) entries = entries.slice(entries.length - history.limit);
  return { ...history, entries, cursor: entries.length - 1 };
}

export function backView(history) {
  if (history.cursor <= 0) return { history, view: null };
  const cursor = history.cursor - 1;
  return { history: { ...history, cursor }, view: history.entries[cursor] };
}

export function forwardView(history) {
  if (history.cursor >= history.entries.length - 1) return { history, view: null };
  const cursor = history.cursor + 1;
  return { history: { ...history, cursor }, view: history.entries[cursor] };
}

// -- Shift+Z: fit -----------------------------------------------------------------

/** Zoom and scroll that show [start, end] with `padding` of the width on both sides. */
export function fitRange({ start, end, width, padding = 0.05 }) {
  const usable = Math.max(1, width * (1 - 2 * padding));
  const zoom = Math.max(SAMPLE_ZOOM, (end - start) / usable);
  return { zoom, scroll: Math.max(0, Math.round(start - padding * width * zoom)) };
}

/** The frames the selected clips cover as { start, end }, or null when none is selected. */
export function selectionSpan(project, selection) {
  let start = Number.POSITIVE_INFINITY;
  let end = 0;
  for (const track of project?.tracks ?? []) {
    for (const clip of track.clips ?? []) {
      if (!selection.has(clip.id)) continue;
      start = Math.min(start, clip.start);
      end = Math.max(end, clip.start + clip.length);
    }
  }
  return Number.isFinite(start) ? { start, end } : null;
}

/** What Shift+Z fits: the selection, else in to out, else the whole edit. */
export function fitTarget({ project, selection, inPoint, outPoint }) {
  const span = selectionSpan(project, selection);
  if (span) return span;
  if (inPoint !== null && outPoint !== null && outPoint > inPoint) {
    return { start: inPoint, end: outPoint };
  }
  return { start: 0, end: projectEnd(project) };
}

// -- the overview strip ---------------------------------------------------------------

/** The box (x, w in strip pixels) that marks the visible part of the whole edit. */
export function overviewWindow({ total, scroll, zoom, width, strip }) {
  if (total <= 0) return { x: 0, w: strip };
  const w = Math.min(strip, Math.max(2, ((width * zoom) / total) * strip));
  const x = Math.max(0, Math.min((scroll / total) * strip, strip - w));
  return { x, w };
}

/** The scroll that centres the visible part on strip pixel `x`. */
export function overviewScroll({ total, zoom, width, strip, x }) {
  const centre = (x / strip) * total;
  return clampScroll(centre - (width * zoom) / 2, zoom, width, total);
}
