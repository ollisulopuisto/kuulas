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

/** Clamp an implicit edge to a serialized clip range (start + length). */
export function clampImplicitEdge(clip, frame, range = null, edge = null) {
  const low = edge === "end" && range ? range[0] + 1 : clip.start;
  const high = edge === "start" && range ? range[1] - 1 : endOf(clip);
  return Math.max(low, Math.min(high, frame));
}

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
export function edgeLimits(
  project,
  track,
  clip,
  edge,
  { ripple, overwrite = false, alone = false },
) {
  const own = sourceSpan(project, clip);
  const end = endOf(clip);
  if (ripple) {
    return edge === "end"
      ? { low: clip.start + 1, high: own.high, neighbour: null }
      : { low: own.low, high: end - 1, neighbour: null };
  }
  if (alone) {
    // Cmd/Ctrl: only this clip. Never rolls a neighbour, never covers one: outwards the edge
    // stops at the nearest clip on the track (a touching one leaves no room).
    let low = Math.max(own.low, 0);
    let high = own.high;
    if (edge === "end") {
      low = clip.start + 1;
      for (const other of track.clips)
        if (other.id !== clip.id && other.start >= end) high = Math.min(high, other.start);
    } else {
      high = end - 1;
      for (const other of track.clips)
        if (other.id !== clip.id && endOf(other) <= clip.start) low = Math.max(low, endOf(other));
    }
    return { low, high, neighbour: null };
  }
  const neighbour = touchingNeighbour(track, clip, edge);
  if (overwrite) {
    // An edge dragged outwards covers the neighbours (they are trimmed or removed), so only
    // the clip's own media bounds it that way; shrinking it still rolls the touching
    // neighbour, which keeps a frame and its own media.
    const theirs = neighbour ? sourceSpan(project, neighbour) : null;
    if (edge === "end")
      return {
        low: Math.max(clip.start + 1, theirs ? Math.max(theirs.low, 0) : 0),
        high: own.high,
        neighbour,
      };
    return {
      low: Math.max(own.low, 0),
      high: Math.min(end - 1, theirs ? theirs.high : end - 1),
      neighbour,
    };
  }
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
export function resolveEdge(
  project,
  track,
  clip,
  edge,
  frame,
  { ripple, overwrite = false, alone = false },
) {
  const { low, high, neighbour } = edgeLimits(project, track, clip, edge, {
    ripple,
    overwrite,
    alone,
  });
  const clamped = Math.max(low, Math.min(Math.max(low, high), Math.round(frame)));
  // Outwards with overwrite on, the neighbour is covered, not rolled.
  const outwards = edge === "end" ? clamped > endOf(clip) : clamped < clip.start;
  return { frame: clamped, neighbour: overwrite && outwards ? null : neighbour, outwards };
}

/**
 * The other clips on the track that the stretch an edge drag covers lies on: `kept` is what
 * stays of each (its edge trimmed), null when it is covered whole and goes. Mirrors
 * ops._overwrite_under, which does the real edit.
 */
export function coveredClips(track, clip, edge, frame) {
  const region =
    edge === "end" ? { start: endOf(clip), end: frame } : { start: frame, end: clip.start };
  const out = [];
  for (const other of track.clips) {
    if (other.id === clip.id) continue;
    const start = other.start;
    const end = endOf(other);
    if (end <= region.start || start >= region.end) continue;
    let kept = null;
    if (start < region.start) kept = { start, end: region.start };
    else if (end > region.end) kept = { start: region.end, end };
    out.push({ id: other.id, start, end, kept });
  }
  return out.sort((a, b) => a.start - b.start);
}

/**
 * What the drag shows, in frames: `line` is the dragged edge, `clip` the dragged
 * clip's new span and `neighbour` the touching clip's new span (roll only).
 * Ripple keeps the clip's start; dragging its start edge shortens it from the head.
 */
export function edgeGhost(
  project,
  track,
  clip,
  edge,
  frame,
  { ripple, overwrite = false, alone = false },
) {
  const resolved = resolveEdge(project, track, clip, edge, frame, { ripple, overwrite, alone });
  const aloneMode = Boolean(alone) && !ripple;
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
  const covering = Boolean(overwrite) && !ripple && !aloneMode && resolved.outwards;
  const region = edge === "end" ? { start: end, end: f } : { start: f, end: clip.start };
  // Alone: the stretch the clip gives up stays empty; the neighbour is not touched.
  const vacated = edge === "end" ? { start: f, end } : { start: clip.start, end: f };
  const gap = aloneMode && vacated.end > vacated.start ? vacated : null;
  return {
    alone: aloneMode,
    gap,
    line: f,
    clip: span,
    neighbour,
    ripple: Boolean(ripple),
    edge,
    overwrite: covering,
    region: covering ? region : null,
    covered: covering ? coveredClips(track, clip, edge, f) : [],
  };
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
    region: ghost.region ? box(ghost.region) : null,
    gap: ghost.gap ? box(ghost.gap) : null,
    covered: (ghost.covered ?? []).map((item) => ({
      ...box(item),
      removed: item.kept === null,
      kept: item.kept ? box(item.kept) : null,
    })),
  };
}

/**
 * The edit to send on release: roll, or ripple while Shift is held. A roll overwrites its
 * neighbours unless Alt was held (`overwrite` false: the edge stops at the neighbour).
 */
export function edgeChange(clipId, edge, frame, ripple, overwrite = true, alone = false) {
  // Priority: ripple, else alone (Cmd/Ctrl: only this clip), else roll.
  if (!ripple && alone) {
    return {
      op: "roll_trim",
      args: { clip_id: clipId, edge, frame, alone: true },
      labelKey: "ui.edge.trim_alone",
    };
  }
  return {
    op: ripple ? "ripple_trim" : "roll_trim",
    // A ripple also gives the material back on the tracks cut at the same splice (the server
    // extends the clips that end there by the same amount): by position, not by sync.
    args: {
      clip_id: clipId,
      edge,
      frame,
      ...(ripple ? { extend_partners: true } : {}),
      ...(!ripple && !overwrite ? { overwrite: false } : {}),
    },
    labelKey: ripple ? "ui.edge.ripple" : "ui.edge.roll",
  };
}

/**
 * Whether a press on a clip edge leaves the selection as it is. Cmd/Ctrl on an edge means
 * "trim only this clip", not "add it to the selection", so it must not toggle anything (the
 * selection stays, the play cursor stays). Cmd+Alt keeps its meaning elsewhere (select this
 * clip and all after it), so that press is not an edge gesture.
 */
export function edgePressKeepsSelection({ mod, alt }) {
  return Boolean(mod) && !alt;
}
