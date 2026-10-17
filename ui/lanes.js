// Lane layout and hit testing: where rows are and what is under a pointer.
// Pure (no DOM), so the same numbers serve the canvas, the track headers
// beside it and the tests.
import { frameToX, xToFrame } from "./format.js";

export const RULER_HEIGHT = 24;
/** tokens.css --bus-h: a two-row group header (name and mute; gain and pan). */
export const BUS_HEIGHT = 44;
export const MIN_LANE = 24;
export const MAX_LANE = 160;
/** tokens.css --lane-h: two header rows (2 × 20 px) plus breathing room. */
export const DEFAULT_LANE = 56;
/** How close (px) a pointer must be to a clip edge or an envelope point. */
export const EDGE_PX = 4;
export const POINT_PX = 6;
// The gain line's range inside a lane: +12 dB at the top, -30 dB at the bottom,
// with a small inset so a point at either end stays inside the lane.
const DB_TOP = 12;
const DB_BOTTOM = -30;
const INSET = 4;

export function clampLaneHeight(height) {
  if (!Number.isFinite(height)) return DEFAULT_LANE;
  return Math.max(MIN_LANE, Math.min(MAX_LANE, height));
}

export function clipEnd(clip) {
  return clip.start + clip.length;
}

export function projectEnd(project) {
  let end = 0;
  for (const track of project?.tracks ?? []) {
    for (const clip of track.clips) end = Math.max(end, clipEnd(clip));
  }
  return end;
}

/**
 * Rows top to bottom, stacked with no gaps; `top` is content y. A bus is a
 * group header above its member tracks (owner, 2026-10-17): it appears where
 * its first member would be, and its members gather under it in track order.
 * Tracks on no bus keep their place. A bus with no members goes last. Rows
 * carry `index` (into project.tracks or project.buses), `bus` (the group a
 * row belongs to) and, on bus rows, `members`.
 */
export function layoutRows(project, laneHeight) {
  const height = clampLaneHeight(laneHeight);
  const tracks = project?.tracks ?? [];
  const buses = project?.buses ?? [];
  const busIndex = new Map(buses.map((bus, i) => [bus.id, i]));
  const members = new Map(buses.map((bus) => [bus.id, []]));
  tracks.forEach((track, i) => {
    if (members.has(track.bus)) members.get(track.bus).push(i);
  });
  const rows = [];
  let top = 0;
  const push = (row) => {
    rows.push({ ...row, top });
    top += row.height;
  };
  const placed = new Set();
  tracks.forEach((track, i) => {
    if (placed.has(i)) return;
    if (members.has(track.bus)) {
      const group = members.get(track.bus);
      push({
        kind: "bus",
        id: track.bus,
        height: BUS_HEIGHT,
        index: busIndex.get(track.bus),
        bus: track.bus,
        members: group.length,
      });
      for (const member of group) {
        push({ kind: "track", id: tracks[member].id, height, index: member, bus: track.bus });
        placed.add(member);
      }
      return;
    }
    push({ kind: "track", id: track.id, height, index: i, bus: null });
    placed.add(i);
  });
  for (const bus of buses) {
    if (members.get(bus.id).length > 0) continue;
    push({
      kind: "bus",
      id: bus.id,
      height: BUS_HEIGHT,
      index: busIndex.get(bus.id),
      bus: bus.id,
      members: 0,
    });
  }
  return { rows, height: top };
}

export function rowAt(layout, y) {
  if (y < 0) return null;
  return layout.rows.find((row) => y >= row.top && y < row.top + row.height) ?? null;
}

/** The rows that overlap the viewport: lists are virtualised, never all drawn. */
export function visibleRows(layout, scrollY, viewHeight) {
  if (viewHeight <= 0) return [];
  return layout.rows.filter(
    (row) => row.top + row.height > scrollY && row.top < scrollY + viewHeight,
  );
}

/** Vertical position of a dB value inside a lane of `height`. */
export function dbToY(db, height) {
  const clamped = Math.max(DB_BOTTOM, Math.min(DB_TOP, db));
  return INSET + ((DB_TOP - clamped) / (DB_TOP - DB_BOTTOM)) * (height - 2 * INSET);
}

export function yToDb(y, height) {
  const t = (y - INSET) / (height - 2 * INSET);
  return Math.max(DB_BOTTOM, Math.min(DB_TOP, DB_TOP - t * (DB_TOP - DB_BOTTOM)));
}

/** Timeline frame of an envelope point (its frame is a *source* frame). */
export function envelopeFrame(clip, sourceFrame) {
  return clip.start + (sourceFrame - clip.offset);
}

/**
 * What is under pixel (x, y) of the timeline canvas.
 *
 * Returns { area: "ruler" | "lane" | "none", frame, row, clip, edge, point }.
 * `edge` is "start" or "end" when the pointer is within EDGE_PX of that edge of
 * `clip`; `point` is the index of the envelope point within POINT_PX.
 */
export function hitTest({ layout, project, view, x, y }) {
  const frame = xToFrame(x, view.scroll, view.zoom);
  const miss = { area: "none", frame, row: null, clip: null, edge: null, point: null };
  if (y < RULER_HEIGHT) return { ...miss, area: y >= 0 ? "ruler" : "none" };
  const inContent = y - RULER_HEIGHT + view.scrollY;
  const row = rowAt(layout, inContent);
  if (!row) return miss;
  const hit = { ...miss, area: "lane", row };
  if (row.kind !== "track") return hit;
  const track = project.tracks.find((candidate) => candidate.id === row.id);
  const rowY = inContent - row.top;
  let best = null;
  for (const clip of track?.clips ?? []) {
    const left = frameToX(clip.start, view.scroll, view.zoom);
    const right = frameToX(clipEnd(clip), view.scroll, view.zoom);
    const toStart = Math.abs(x - left);
    const toEnd = Math.abs(x - right);
    const inside = x >= left && x < right;
    const edge = Math.min(toStart, toEnd) <= EDGE_PX ? (toStart <= toEnd ? "start" : "end") : null;
    if (!inside && !edge) continue;
    // Where two clips touch, the nearer edge wins; otherwise the one the pointer is inside.
    const distance = edge ? Math.min(toStart, toEnd) : EDGE_PX + 1;
    if (!best || distance < best.distance) best = { clip, edge, distance };
  }
  if (!best) return hit;
  const point = envelopePointAt(best.clip, view, x, rowY, row.height);
  return { ...hit, clip: best.clip, edge: best.edge, point };
}

function envelopePointAt(clip, view, x, rowY, rowHeight) {
  let nearest = null;
  for (const [index, [sourceFrame, db]] of (clip.envelope ?? []).entries()) {
    const px = frameToX(envelopeFrame(clip, sourceFrame), view.scroll, view.zoom);
    const py = dbToY((clip.gain_db ?? 0) + db, rowHeight);
    const distance = Math.hypot(px - x, py - rowY);
    if (distance <= POINT_PX && (!nearest || distance < nearest.distance))
      nearest = { index, distance };
  }
  return nearest ? nearest.index : null;
}
