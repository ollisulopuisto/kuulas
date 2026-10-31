// Dragging a clip's gain line and fade handles (WP6). Pure: what the pointer hits, the value
// it gives and the edit to send. Both edits are `set_clip` with a coalesce key, so a whole
// drag is one undo step; the keyboard (+/-, Mod+F) and the inspector set the same fields.
import { lineValueAt, movePoint, togglePoint } from "./envelope-edit.js";
import { dbToY, yToDb } from "./lanes.js";

/** How close (px) the pointer must be to the gain line. */
export const GAIN_HIT_PX = 5;
/** The line and the handles are drawn only in lanes at least this tall (timeline.js). */
export const MIN_LANE_FOR_HANDLES = 40;
/** Handle radius (px) for hit testing, and how far in from the corner a handle sits at rest. */
export const FADE_HIT_PX = 6;
export const FADE_INSET_PX = 10;
/** Handle height in the lane (px from the lane's top): just under the clip's top edge. */
export const FADE_HANDLE_Y = 7;

/** The gain line shows when it says something (not 0 dB, an envelope) or the clip is selected. */
export function gainLineVisible(clip, selected) {
  return (clip.gain_db ?? 0) !== 0 || (clip.envelope?.length ?? 0) > 0 || Boolean(selected);
}

/** True when `rowY` (px from the lane's top) is on the clip's gain line. */
export function gainLineHit(clip, rowHeight, rowY) {
  if (rowHeight < MIN_LANE_FOR_HANDLES) return false;
  return Math.abs(rowY - dbToY(clip.gain_db ?? 0, rowHeight)) <= GAIN_HIT_PX;
}

/**
 * Double-click on a clip's gain line (the envelope, drawn at the clip gain plus the envelope's
 * dB): add a point where the line is, or remove the point under the pointer.
 *
 * `at` = { timelineFrame, rowHeight, rowY, point }: the pointer's timeline frame, the lane's
 * height, the pointer's y in the lane and hitTest's `point` (index of the envelope point under
 * the pointer, or null). Envelope frames are SOURCE frames (lanes.js envelopeFrame is
 * start + (frame - offset)), so the timeline frame is converted back here. A new point takes
 * the line's current value, so adding one does not change the sound.
 * Returns { points, action: "added" | "removed" } or null when the pointer is not near the
 * line (the caller then leaves the double-click to whatever else it means).
 */
export function envelopeToggle(clip, { timelineFrame, rowHeight, rowY, point }) {
  if (rowHeight < MIN_LANE_FOR_HANDLES) return null;
  const envelope = clip.envelope ?? [];
  if (point != null && envelope[point]) {
    return togglePoint(envelope, envelope[point][0], 0, 0);
  }
  const sourceFrame = Math.round(clip.offset + (timelineFrame - clip.start));
  const db = Math.round(lineValueAt(envelope, sourceFrame) * 10) / 10;
  const lineY = dbToY((clip.gain_db ?? 0) + lineValueAt(envelope, sourceFrame), rowHeight);
  if (Math.abs(rowY - lineY) > GAIN_HIT_PX) return null;
  return togglePoint(envelope, sourceFrame, db, 0);
}

/** The edit for a double-click on the gain line: one set_clip_envelope, one undo step. */
export function envelopeChange(clipId, points) {
  return {
    op: "set_clip_envelope",
    args: { clip_id: clipId, points },
    labelKey: "ui.clipdrag.envelope",
  };
}

/** The coalescing key used by every update in one point drag. */
export function envelopeDragChange(clipId, points) {
  return {
    ...envelopeChange(clipId, points),
    coalesce: `clip-envelope-${clipId}`,
  };
}

/** A hit point on a clip, with trim edges retaining priority. */
export function envelopePointZone(hit) {
  if (
    !hit?.clip ||
    hit.row?.kind !== "track" ||
    hit.edge ||
    !Number.isInteger(hit.point) ||
    !hit.clip.envelope?.[hit.point]
  ) {
    return null;
  }
  return { kind: "envelope", point: hit.point };
}

/** Move an envelope point from pointer coordinates, preserving where it was grabbed. */
export function envelopeMove(
  clip,
  index,
  { timelineFrame, rowHeight, rowY, grabFrames = 0, grabY = 0 },
) {
  const points = clip.envelope ?? [];
  if (rowHeight < MIN_LANE_FOR_HANDLES || !points[index]) return points;

  const timeline = Math.max(
    clip.start,
    Math.min(clip.start + clip.length, timelineFrame - grabFrames),
  );
  const sourceFrame = Math.round(clip.offset + (timeline - clip.start));
  const db = Math.round((yToDb(rowY - grabY, rowHeight) - (clip.gain_db ?? 0)) * 10) / 10;
  return movePoint(points, index, sourceFrame, db);
}

/** How far (px) below the line the press landed, so the line does not jump to the pointer. */
export function gainGrab(clip, rowHeight, rowY) {
  return rowY - dbToY(clip.gain_db ?? 0, rowHeight);
}

/** The gain (dB, 0.1 steps) for the pointer at `rowY`, within the lane's +12 to -30 dB. */
export function gainFromY(rowHeight, rowY, grab) {
  return Math.round(yToDb(rowY - grab, rowHeight) * 10) / 10;
}

/** The edit for one step of the drag. */
export function gainChange(clipId, gainDb) {
  return {
    op: "set_clip",
    args: { clip_id: clipId, gain_db: gainDb },
    coalesce: `clip-gain-${clipId}`,
    labelKey: "ui.clipdrag.gain",
  };
}

const fadePixels = (clip, side, zoom) => (clip[`fade_${side}`] ?? 0) / zoom;

/**
 * Handle centres in lane pixels: `frame` is { left, right, zoom } of the clip on screen.
 * A handle sits at the end of its fade, but never closer to the corner than FADE_INSET_PX.
 */
export function fadeHandles(clip, { left, right, zoom }) {
  return {
    in: { x: left + Math.max(FADE_INSET_PX, fadePixels(clip, "in", zoom)), y: FADE_HANDLE_Y },
    out: { x: right - Math.max(FADE_INSET_PX, fadePixels(clip, "out", zoom)), y: FADE_HANDLE_Y },
  };
}

/** "in", "out" or null: the fade handle at (x, rowY); none in a short lane or a narrow clip. */
export function fadeHandleAt(clip, frame, x, rowY, rowHeight) {
  if (rowHeight < MIN_LANE_FOR_HANDLES) return null;
  if (frame.right - frame.left < 4 * FADE_INSET_PX) return null;
  const handles = fadeHandles(clip, frame);
  for (const side of ["in", "out"]) {
    if (Math.hypot(x - handles[side].x, rowY - handles[side].y) <= FADE_HIT_PX) return side;
  }
  return null;
}

/**
 * The fade length (frames) for the pointer at `x`: the fade the drag started with, moved by
 * the pointer's travel. Whole frames, within the clip less the other fade.
 */
export function fadeFromX(clip, side, { startFade, startX, x, zoom }) {
  const other = clip[side === "in" ? "fade_out" : "fade_in"] ?? 0;
  const travel = (x - startX) * zoom * (side === "in" ? 1 : -1);
  return Math.max(0, Math.min(clip.length - other, Math.round(startFade + travel)));
}

/**
 * The fade's ghost: a line from the clip's bottom corner up to where the fade ends.
 * `frame` as in fadeHandles plus the clip box's `top` and `height` in the same pixels.
 */
export function fadeShape(clip, side, { left, right, zoom, top, height }) {
  const px = fadePixels(clip, side, zoom);
  const bottom = top + height;
  return side === "in"
    ? [
        [left, bottom],
        [left + px, top],
      ]
    : [
        [right, bottom],
        [right - px, top],
      ];
}

/** The edit for one step of a fade drag. */
export function fadeChange(clipId, side, frames) {
  return {
    op: "set_clip",
    args: { clip_id: clipId, [`fade_${side}`]: frames },
    coalesce: `clip-fade_${side}-${clipId}`,
    labelKey: `ui.clipdrag.fade_${side}`,
  };
}
