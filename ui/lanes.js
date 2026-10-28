// Lane layout and hit testing: where rows are and what is under a pointer.
// Pure (no DOM), so the same numbers serve the canvas, the track headers
// beside it and the tests.

import { implicitPortions } from "./clip-silence.js";
import { frameToX, xToFrame } from "./format.js";
import { stretchAt } from "./gate.js";
import { markerIdAtX } from "./markers-model.js";
import { placeholderAt } from "./placeholders-model.js";

export const RULER_HEIGHT = 24;
/** tokens.css --bus-h: a bus is ONE short line (disclosure, badge, name, M, S);
 *  its levels show on hover and in the inspector (owner, 2026-10-18). Compact: 24. */
export const BUS_HEIGHT = 68;
/** tokens.css --group-gap: plain lane between groups, so each bus reads as a block. Compact: 6. */
export const GROUP_GAP = 14;
export const MIN_LANE = 24;
export const MAX_LANE = 360;
/** tokens.css --lane-h (comfortable): room for the name row at rest and the
 *  level row on the current track. Compact: 40. */
export const DEFAULT_LANE = 80;
/** How close (px) a pointer must be to a clip edge or an envelope point. */
export const EDGE_PX = 6;
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
 * Rows top to bottom, stacked; `top` is content y. A bus is a group header
 * above its member tracks (owner, 2026-10-17): it appears where its first
 * member would be, and its members gather under it in track order. Tracks on
 * no bus keep their place. A bus with no members goes last. Between groups
 * (a bus block and the next row of another group or of no group) sits a
 * `gap` row of plain lane (owner, 2026-10-18). Rows carry `index` (into
 * project.tracks or project.buses), `bus` (the group a row belongs to),
 * `last` on a group's last member (where the spine ends), and on bus rows
 * `members`. With `mergeSingle`, a bus with exactly one member has no row of
 * its own: the member is marked `merged` and carries the bus identity.
 * `options.laneHeights` ({ trackId: px }) gives single tracks their own height
 * (clamped); a track without an entry uses `laneHeight`.
 * `options.viewHeights` ({ trackId: px }, focus mode's view layer, focus-layout.js) wins over
 * both and is not clamped up to MIN_LANE, so a lane can be a 16 px strip.
 * `options.collapsed` (a Set of bus ids) folds a bus: its row stays (marked
 * `collapsed`, with `memberIndexes` into project.tracks for the summary strip)
 * and its member tracks get no rows. A merged one-track bus has no row to fold.
 */
export function layoutRows(project, laneHeight, options = {}) {
  const height = clampLaneHeight(laneHeight);
  const busHeight = options.busHeight ?? BUS_HEIGHT;
  const groupGap = options.groupGap ?? GROUP_GAP;
  const own = options.laneHeights ?? {};
  const collapsed = options.collapsed ?? new Set();
  const view = options.viewHeights ?? {};
  const heightOf = (id) => {
    if (Number.isFinite(view[id])) return Math.max(1, Math.round(view[id]));
    return Number.isFinite(own[id]) ? clampLaneHeight(own[id]) : height;
  };
  const tracks = project?.tracks ?? [];
  const buses = project?.buses ?? [];
  const busIndex = new Map(buses.map((bus, i) => [bus.id, i]));
  const members = new Map(buses.map((bus) => [bus.id, []]));
  tracks.forEach((track, i) => {
    if (members.has(track.bus)) members.get(track.bus).push(i);
  });
  const rows = [];
  let top = 0;
  let group;
  const push = (row) => {
    // A gap wherever the group changes, never above the first row.
    if (rows.length > 0 && row.bus !== group && groupGap > 0) {
      rows.push({ kind: "gap", id: `gap:${rows.length}`, top, height: groupGap, bus: null });
      top += groupGap;
    }
    group = row.bus;
    rows.push({ ...row, top });
    top += row.height;
  };
  const placed = new Set();
  tracks.forEach((track, i) => {
    if (placed.has(i)) return;
    if (members.has(track.bus)) {
      const group = members.get(track.bus);
      const merged = Boolean(options.mergeSingle) && group.length === 1;
      const folded = !merged && collapsed.has(track.bus);
      if (!merged) {
        push({
          kind: "bus",
          id: track.bus,
          height: busHeight,
          index: busIndex.get(track.bus),
          bus: track.bus,
          members: group.length,
          collapsed: folded,
          memberIndexes: group,
        });
      }
      if (folded) {
        for (const member of group) placed.add(member);
        return;
      }
      group.forEach((member, n) => {
        const row = {
          kind: "track",
          id: tracks[member].id,
          height: heightOf(tracks[member].id),
          index: member,
          bus: track.bus,
          last: n === group.length - 1,
        };
        if (merged) row.merged = true;
        push(row);
        placed.add(member);
      });
      return;
    }
    push({
      kind: "track",
      id: track.id,
      height: heightOf(track.id),
      index: i,
      bus: null,
      last: false,
    });
    placed.add(i);
  });
  for (const bus of buses) {
    if (members.get(bus.id).length > 0) continue;
    push({
      kind: "bus",
      id: bus.id,
      height: busHeight,
      index: busIndex.get(bus.id),
      bus: bus.id,
      members: 0,
      collapsed: false,
      memberIndexes: [],
    });
  }
  return { rows, height: top };
}

/** The layout for the client state: its lane, bus and gap sizes (density), one-track buses merged. */
export function layoutFor(state) {
  return layoutRows(state.project, state.laneHeight, {
    busHeight: state.busHeight,
    groupGap: state.groupGap,
    // A bus with one track merges into the track header (owner, 2026-10-18).
    mergeSingle: true,
    laneHeights: state.laneHeights,
    // Focus mode (WP28): the focused lanes grown, the others strips; a view layer only.
    viewHeights: state.focusHeights ?? undefined,
    collapsed: state.collapsedBuses,
  });
}

/**
 * What a primary click does (owner, 2026-10-18). Anywhere in the lane area
 * (a clip, an empty stretch, a bus row, a group gap, below the last track)
 * sets the play cursor; a clip is also selected. Shift+click only toggles the
 * selection and never moves the cursor. The ruler seeks and keeps the
 * selection. Returns { seek: frame | null, selection: "replace" | "toggle" |
 * "clear" | "keep", clip } or null when the click is outside.
 */
export function pointerIntent(hit, { shift = false, mod = false, alt = false } = {}) {
  if (!hit || hit.area === "none") return null;
  if (hit.area === "ruler") return { seek: hit.frame, selection: "keep", clip: null };
  const clip = hit.clip ?? null;
  // Shift+click and Mod+click both toggle the clicked clip and leave the cursor alone.
  if (shift || mod) return { seek: null, selection: clip ? "toggle" : "keep", clip };
  // Plain Alt+click on a clip leaves cursor and selection alone (direct mute).
  if (alt && clip) return { seek: null, selection: "keep", clip, mute: true };
  return { seek: hit.frame, selection: clip ? "replace" : "clear", clip };
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
 * Returns { area: "ruler" | "lane" | "none", frame, row, clip, edge, point, gate, placeholder }
 * (`gate` is { trackId, index, range } over a closed stretch, else null; `placeholder` is the
 * narration placeholder (WP43) under the pointer on that track, else null).
 * `edge` is "start" or "end" when the pointer is within EDGE_PX of that edge of
 * `clip`; `point` is the index of the envelope point within POINT_PX.
 */
export function hitTest({ layout, project, view, x, y }) {
  const frame = xToFrame(x, view.scroll, view.zoom);
  const miss = {
    area: "none",
    frame,
    row: null,
    clip: null,
    edge: null,
    point: null,
    gate: null,
    placeholder: null,
    autoPoint: null,
  };
  if (y < RULER_HEIGHT)
    return {
      ...miss,
      area: y >= 0 ? "ruler" : "none",
      marker: y >= 0 ? markerIdAtX(project.markers, view, x) : null,
    };
  const inContent = y - RULER_HEIGHT + view.scrollY;
  const row = rowAt(layout, inContent);
  // Below the last row is still lane area: a click there sets the cursor.
  if (!row) return { ...miss, area: "lane" };
  const track = project.tracks.find((candidate) => candidate.id === row.id);
  // A closed stretch of the gate (WP44), unless the user hides gates.
  const gate =
    row.kind === "track" && view.showGates !== false
      ? stretchAt(project, row.id, frame, view.zoom)
      : null;
  const placeholder =
    row.kind === "track" ? placeholderAt(project.placeholders, row.id, frame) : null;
  const hit = { ...miss, area: "lane", row, gate, placeholder };
  if (row.kind !== "track") return hit;
  const rowY = inContent - row.top;
  hit.autoPoint = automationPointAt(track, view, x, rowY, row.height);
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
    // Overlapping clips at the pointer: the shorter one is the more specific, and the later one
    // in the list is drawn on top. Neither may hide the other (owner, 2026-10-18).
    const wins =
      !best ||
      distance < best.distance ||
      (distance === best.distance && !edge && !best.edge && clip.length <= best.clip.length);
    if (wins) best = { clip, edge, distance };
  }
  if (!best) return hit;
  const point = envelopePointAt(best.clip, view, x, rowY, row.height);
  const portions = view.showGates === false ? [] : implicitPortions(best.clip, track.gate);
  const portionFrame = Math.max(best.clip.start, Math.min(frame, clipEnd(best.clip) - 1));
  const portion = portions.find(({ range: [a, b] }) => a <= portionFrame && portionFrame < b);
  let implicitRange = null;
  let edge = best.edge;
  if (portion) {
    const [start, end] = portion.range;
    const toStart = Math.abs(x - frameToX(start, view.scroll, view.zoom));
    const toEnd = Math.abs(x - frameToX(end, view.scroll, view.zoom));
    if (Math.min(toStart, toEnd) <= EDGE_PX) {
      edge = toStart <= toEnd ? "start" : "end";
      implicitRange = portion.range;
    }
  }
  const implicit = portion
    ? {
        trackId: row.id,
        clipId: best.clip.id,
        index: portions.indexOf(portion),
        ...portion,
        implicit: true,
      }
    : null;
  return {
    ...hit,
    clip: best.clip,
    edge,
    point,
    ...(implicitRange ? { implicitRange } : {}),
    gate: implicit ?? gate,
  };
}

/**
 * The order clips are painted in: long ones first, so a short clip lying inside a long one is
 * drawn on top, and is the one hitTest picks (a stable sort: ties keep the list order).
 */
export function paintOrder(clips) {
  return [...(clips ?? [])].sort((a, b) => b.length - a.length);
}

/**
 * The index of the track's ducking (automation) point within POINT_PX of the pointer, or null.
 * The geometry is timeline.js drawAutomation's: a line in the lower third of a lane that is
 * at least 40 px high, 0 dB at the top of the band, -24 dB at its foot.
 */
export function automationPointAt(track, view, x, rowY, rowHeight) {
  if (!track?.automation?.length || rowHeight < 40) return null;
  const bottom = rowHeight - 3;
  const band = rowHeight / 3 - 4;
  let nearest = null;
  for (const [index, [frame, db]] of track.automation.entries()) {
    const px = frameToX(frame, view.scroll, view.zoom);
    const py = bottom - band * (1 - Math.max(-24, Math.min(0, db)) / -24);
    const distance = Math.hypot(px - x, py - rowY);
    if (distance <= POINT_PX && (!nearest || distance < nearest.distance))
      nearest = { index, distance };
  }
  return nearest ? nearest.index : null;
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
