// Dragging a clip body to move it (WP6): in time and onto another track. Pure: the grab zone,
// which track is under the pointer, how far the clips may go, the ghosts and the edit. Moving
// is `move_clips_to_track` (ops.py), a nudge plus a track change; sync partners and the group
// setting follow the server's nudge rule, so nothing about groups is decided here.
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

/** The clips a drag of `pressedId` moves: the selection if it holds that clip, else the clip. */
export function clipDragIds(pressedId, selection) {
  return selection?.has(pressedId) ? [...selection] : [pressedId];
}

/**
 * The clip whose track change counts: the pressed one while group editing is on and Alt is up
 * (then every other clip follows in time only), else null (the selection keeps its shape).
 */
export function dragAnchor(pressedId, groupEditing, alone) {
  return groupEditing && !alone ? pressedId : null;
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
 * keeps its shape). With an `anchorId` only that clip changes track, so only it limits the
 * track change. The same clamps as ops.move_clips_to_track, so the ghost is the result.
 */
export function resolveMove(project, ids, { deltaFrames, fromIndex, toIndex }, anchorId = null) {
  const chosen = located(project, ids);
  if (chosen.length === 0) return { delta: 0, direction: 0 };
  const earliest = Math.min(...chosen.map((entry) => entry.clip.start));
  const delta = Math.max(Math.round(deltaFrames), -earliest);
  const anchored = anchorId === null ? [] : chosen.filter((entry) => entry.clip.id === anchorId);
  const rows = (anchored.length > 0 ? anchored : chosen).map((entry) => entry.index);
  const direction = Math.max(
    -Math.min(...rows),
    Math.min(project.tracks.length - 1 - Math.max(...rows), toIndex - fromIndex),
  );
  return { delta: delta || 0, direction: direction || 0 }; // `|| 0`: never -0
}

/** Where each dragged clip ends up: { clipId, trackId, start, end } in frames. */
export function moveGhosts(project, ids, { delta, direction }, anchorId = null) {
  return located(project, ids).map(({ clip, index }) => ({
    clipId: clip.id,
    trackId: project.tracks[index + (anchorId === null || clip.id === anchorId ? direction : 0)].id,
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
export function clipDragChange(ids, { delta, direction }, groupEditing, anchorId = null) {
  if (delta === 0 && direction === 0) return null;
  const args = { clip_ids: ids, direction, delta, group_editing: Boolean(groupEditing) };
  if (anchorId !== null) args.anchor_clip_id = anchorId;
  return {
    op: "move_clips_to_track",
    args,
    labelKey: "ui.clipdrag.move",
  };
}
