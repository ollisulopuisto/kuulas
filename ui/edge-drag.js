// Dragging a clip's edge (WP6). Pure: which clip touches the edge, where the
// edge may go, what the ghost looks like, and the edit to send. The rules mirror
// ops.roll_trim / ops.ripple_trim, so the ghost shows what the edit will do;
// the server clamps again and has the last word.
import { frameToX } from "./format.js";
import { RULER_HEIGHT } from "./lanes.js";

/** Pointer travel (px) before a press on an edge becomes a drag; less is a click. */
export const DRAG_PX = 4;

export function isDrag(dx, dy, threshold = DRAG_PX) {
  return Math.hypot(dx, dy) >= threshold;
}

const endOf = (clip) => clip.start + clip.length;

/** The clip on the same track that meets `clip` exactly at `edge`, or null. */
export function touchingNeighbour(track, clip, edge) {
  for (const other of track.clips) {
    if (other.id === clip.id) continue;
    if (edge === "end" && other.start === endOf(clip)) return other;
    if (edge === "start" && endOf(other) === clip.start) return other;
  }
  return null;
}

/** The timeline frames a clip can reach without source before or after its media. */
function sourceSpan(project, clip) {
  const media = project.media.find((item) => item.id === clip.media);
  const origin = clip.start - clip.offset;
  return { low: origin, high: origin + (media?.frames ?? clip.offset + clip.length) };
}

/**
 * Where `edge` of `clip` may be dragged: { low, high, neighbour }. Roll keeps one
 * frame in each clip it changes and stays inside their media; with no touching
 * neighbour it also stops at the next clip on the track instead of overlapping it.
 * Ripple only needs the clip's own media and one frame (its start stays put).
 */
export function edgeLimits(project, track, clip, edge, { ripple }) {
  const own = sourceSpan(project, clip);
  const end = endOf(clip);
  if (ripple) {
    return edge === "end"
      ? { low: clip.start + 1, high: own.high, neighbour: null }
      : { low: own.low, high: end - 1, neighbour: null };
  }
  const neighbour = touchingNeighbour(track, clip, edge);
  let low = Math.max(own.low, 0);
  let high = own.high;
  if (edge === "end") low = clip.start + 1;
  else high = end - 1;
  if (neighbour) {
    const theirs = sourceSpan(project, neighbour);
    if (edge === "end") {
      low = Math.max(low, theirs.low, 0);
      high = Math.min(high, endOf(neighbour) - 1);
    } else {
      low = Math.max(low, neighbour.start + 1);
      high = Math.min(high, theirs.high);
    }
  } else if (edge === "end") {
    for (const other of track.clips)
      if (other.id !== clip.id && other.start >= end) high = Math.min(high, other.start);
  } else {
    for (const other of track.clips)
      if (other.id !== clip.id && endOf(other) <= clip.start) low = Math.max(low, endOf(other));
  }
  return { low, high, neighbour };
}

/** The edge's new frame (whole, clamped) and the neighbour it moves, if any. */
export function resolveEdge(project, track, clip, edge, frame, { ripple }) {
  const { low, high, neighbour } = edgeLimits(project, track, clip, edge, { ripple });
  const clamped = Math.max(low, Math.min(Math.max(low, high), Math.round(frame)));
  return { frame: clamped, neighbour };
}

/**
 * What the drag shows, in frames: `line` is the dragged edge, `clip` the dragged
 * clip's new span and `neighbour` the touching clip's new span (roll only).
 * Ripple keeps the clip's start; dragging its start edge shortens it from the head.
 */
export function edgeGhost(project, track, clip, edge, frame, { ripple }) {
  const resolved = resolveEdge(project, track, clip, edge, frame, { ripple });
  const f = resolved.frame;
  const end = endOf(clip);
  const nb = resolved.neighbour;
  let span;
  if (ripple)
    span =
      edge === "end"
        ? { start: clip.start, end: f }
        : { start: clip.start, end: end - (f - clip.start) };
  else span = edge === "end" ? { start: clip.start, end: f } : { start: f, end };
  let neighbour = null;
  if (nb) {
    neighbour = edge === "end" ? { start: f, end: endOf(nb) } : { start: nb.start, end: f };
  }
  return { line: f, clip: span, neighbour, ripple: Boolean(ripple), edge };
}

/** The ghost in canvas pixels for the lane `row`: the line spans the lane, outlines match clips. */
export function ghostGeometry(ghost, { view, row }) {
  const top = RULER_HEIGHT + row.top - view.scrollY;
  const box = (span) => {
    const x = frameToX(span.start, view.scroll, view.zoom);
    return {
      x,
      y: top + 2,
      w: Math.max(1, frameToX(span.end, view.scroll, view.zoom) - x),
      h: row.height - 4,
    };
  };
  return {
    line: { x: frameToX(ghost.line, view.scroll, view.zoom), y: top, h: row.height },
    clip: box(ghost.clip),
    neighbour: ghost.neighbour ? box(ghost.neighbour) : null,
  };
}

/** The edit to send on release: roll, or ripple while Shift is held. */
export function edgeChange(clipId, edge, frame, ripple) {
  return {
    op: ripple ? "ripple_trim" : "roll_trim",
    // A ripple also gives the material back on the tracks cut at the same splice (the server
    // extends the clips that end there by the same amount): by position, not by sync.
    args: { clip_id: clipId, edge, frame, ...(ripple ? { extend_partners: true } : {}) },
    labelKey: ripple ? "ui.edge.ripple" : "ui.edge.roll",
  };
}
