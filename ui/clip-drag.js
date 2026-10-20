// Dragging a clip body to move it (WP6): in time and onto another track. Pure: the grab zone,
// which track is under the pointer, how far the clips may go, the ghosts and the edit. Moving
// is `move_clips_to_track` (ops.py), a nudge plus a track change; sync partners and the group
// setting follow the server's nudge rule, so nothing about groups is decided here.
import { expandGroups } from "./clip-groups.js";
import { frameToX } from "./format.js";
import { RULER_HEIGHT } from "./lanes.js";

/**
 * Height (px, from the lane's top) of the grab strip: the clip's label row. A drag on the
 * waveform below it stays the range drag (range-drag.js), as the plan recommends.
 */
export const MOVE_STRIP_PX = 20;

/** True when `rowY` (px from the lane's top) is inside the clip's label strip. */
export function inMoveZone(rowY) {
  return rowY >= 0 && rowY < MOVE_STRIP_PX;
}

/**
 * A press may start a move anywhere on a clip's body (Hindenburg's way, owner 2026-10-18):
 * not on its trim edges or an envelope point. A range over a clip takes Shift+drag.
 */
export function canStartClipDrag(hit) {
  if (!hit?.clip || hit.row?.kind !== "track") return false;
  return hit.edge == null && hit.point == null;
}

/**
 * The clips a drag of `pressedId` moves: the selection if it holds that clip, else the clip,
 * plus every member of an explicit group among them (as the server's `expand_clips`, WP83),
 * so the ghosts show the whole group whichever member was grabbed.
 */
export function clipDragIds(pressedId, selection, project = null) {
  const base = selection?.has(pressedId) ? [...selection] : [pressedId];
  return project ? [...expandGroups(project, base)] : base;
}

/** The outline round all ghost boxes (canvas pixels), or null for fewer than two boxes. */
export function groupBounds(boxes) {
  if (boxes.length < 2) return null;
  const x = Math.min(...boxes.map((box) => box.x));
  const y = Math.min(...boxes.map((box) => box.y));
  return {
    x,
    y,
    w: Math.max(...boxes.map((box) => box.x + box.w)) - x,
    h: Math.max(...boxes.map((box) => box.y + box.h)) - y,
  };
}

function distanceToRow(row, contentY) {
  if (contentY < row.top) return row.top - contentY;
  if (contentY >= row.top + row.height) return contentY - (row.top + row.height) + 1;
  return 0;
}

/**
 * The track row for content y: the one under it, else the nearest (a bus or gap row between
 * tracks, above the first, below the last). Null when there are no track rows.
 */
export function targetTrackRow(layout, contentY) {
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const row of layout.rows) {
    if (row.kind !== "track") continue;
    const distance = distanceToRow(row, contentY);
    if (distance < bestDistance) {
      best = row;
      bestDistance = distance;
    }
  }
  return best;
}

function located(project, ids) {
  const found = [];
  for (const [index, track] of project.tracks.entries())
    for (const clip of track.clips) if (ids.includes(clip.id)) found.push({ clip, index });
  return found;
}

/**
 * { delta, direction } for the pointer's travel: whole frames, the earliest clip stops at
 * frame 0, and the track change is cut back until every clip is on a track (the selection
 * keeps its shape). The same clamps as ops.move_clips_to_track, so the ghost is the result.
 */
export function resolveMove(project, ids, { deltaFrames, fromIndex, toIndex }) {
  const chosen = located(project, ids);
  if (chosen.length === 0) return { delta: 0, direction: 0 };
  const earliest = Math.min(...chosen.map((entry) => entry.clip.start));
  const delta = Math.max(Math.round(deltaFrames), -earliest);
  const rows = chosen.map((entry) => entry.index);
  const direction = Math.max(
    -Math.min(...rows),
    Math.min(project.tracks.length - 1 - Math.max(...rows), toIndex - fromIndex),
  );
  return { delta: delta || 0, direction: direction || 0 }; // `|| 0`: never -0
}

/** Where each dragged clip ends up: { clipId, trackId, start, end } in frames. */
export function moveGhosts(project, ids, { delta, direction }) {
  return located(project, ids).map(({ clip, index }) => ({
    clipId: clip.id,
    trackId: project.tracks[index + direction].id,
    start: clip.start + delta,
    end: clip.start + delta + clip.length,
  }));
}

/** The ghosts in canvas pixels, in the lane of their new track (outlines like the clips'). */
export function moveBoxes(ghosts, { view, layout }) {
  const boxes = [];
  for (const ghost of ghosts) {
    const row = layout.rows.find((item) => item.kind === "track" && item.id === ghost.trackId);
    if (!row) continue;
    const x = frameToX(ghost.start, view.scroll, view.zoom);
    boxes.push({
      clipId: ghost.clipId,
      x,
      y: RULER_HEIGHT + row.top - (view.scrollY ?? 0) + 2,
      w: Math.max(1, frameToX(ghost.end, view.scroll, view.zoom) - x),
      h: row.height - 4,
    });
  }
  return boxes;
}

/** The edit to send on release, or null when the clips did not move. */
export function clipDragChange(ids, { delta, direction }) {
  if (delta === 0 && direction === 0) return null;
  return {
    op: "move_clips_to_track",
    args: { clip_ids: ids, direction, delta },
    labelKey: "ui.clipdrag.move",
  };
}
