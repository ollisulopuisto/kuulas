// Dragging a time range in the lanes (WP6, owner 2026-10-18): press, move, lift sets the
// in and out marks, so X, Backspace, Mod+C, Play selection and the loop act on it exactly
// as on marks set with I and O. Pure (no DOM): the pointer wiring lives in timeline.js.
import { clipsInRange, rangeFromClips } from "./selection-ops.js";

/** Movement (px) before a press becomes a drag; less is still the plain click. */
export const DRAG_PX = 4;

/** True once the pointer has moved DRAG_PX or more from where it was pressed. */
export function isDrag(from, to) {
  return Math.hypot(to.x - from.x, to.y - from.y) >= DRAG_PX;
}

/**
 * The marks for a drag between two frames, in either direction, clamped to the project
 * (0..projectFrames) and rounded to whole frames. Null when nothing is left (start == end).
 */
export function dragRange(fromFrame, toFrame, projectFrames) {
  const clamp = (frame) => Math.max(0, Math.min(projectFrames, Math.round(frame)));
  const a = clamp(fromFrame);
  const b = clamp(toFrame);
  return a === b ? null : { start: Math.min(a, b), end: Math.max(a, b) };
}

/** Ids of the track rows (top to bottom) the vertical extent y0..y1 (content y, any order) touches. */
export function trackRowsTouched(layout, y0, y1) {
  const top = Math.min(y0, y1);
  const bottom = Math.max(y0, y1);
  return layout.rows
    .filter((row) => row.kind === "track" && row.top <= bottom && row.top + row.height > top)
    .map((row) => row.id);
}

/**
 * A press may start a range drag in a track's empty part, or over a clip with Shift held (a
 * plain drag on a clip moves it, as in Hindenburg; so does Alt), but not on a clip's trim zone or an
 * envelope point (those keep their own behaviour), the ruler or a bus row.
 */
export function canStartRangeDrag(hit, shift = false, alt = false) {
  if (!hit || hit.area !== "lane" || hit.row?.kind !== "track") return false;
  if (hit.edge != null || hit.point != null) return false;
  return hit.clip == null || shift === true || alt === true;
}

/** Ids of the clips the range touches on the given tracks (what holding Alt highlights). */
export function touchedClips(project, range, trackIds) {
  return clipsInRange(project, range, trackIds);
}

/**
 * What releasing a range drag with Alt held makes of it: the touched clips as the selection,
 * the marks at the span of those clips, and the tracks holding them (project order). Null
 * when the range touches no clip: the exact range then stays as dragged.
 */
export function touchedResult(project, range, trackIds) {
  const selection = touchedClips(project, range, trackIds);
  const span = rangeFromClips(project, selection);
  if (!span) return null;
  const tracks = project.tracks
    .filter((track) => track.clips.some((clip) => selection.has(clip.id)))
    .map((track) => track.id);
  return { selection, start: span.start, end: span.end, tracks };
}
