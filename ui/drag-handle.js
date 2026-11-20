// The one drag-handle design (owner, 2026-11-20): hovering a draggable edge shows a thicker
// teal edge and a small grip pill; at rest nothing shows. Pure geometry and hover decisions
// for the timeline canvas (clip trims and silence cuts, fade ends); the lane grip mirrors the
// same look in style.css (.lane-grip:hover).
export const PILL_WIDTH = 26;
export const PILL_HEIGHT = 12;
export const EDGE_PX = 3; // the hovered edge's teal line: thicker than the 1 px resting border
const BAR_WIDTH = 2;
const BAR_PITCH = 6; // three bars across the pill's middle
const BAR_HEIGHT = 6;

/** The pill centred at (cx, cy): its box and each grip bar's geometry. */
export function gripPill(cx, cy) {
  return {
    x: cx - PILL_WIDTH / 2,
    y: cy - PILL_HEIGHT / 2,
    width: PILL_WIDTH,
    height: PILL_HEIGHT,
    radius: PILL_HEIGHT / 2,
    bars: [-1, 0, 1].map((i) => cx + i * BAR_PITCH - BAR_WIDTH / 2),
    barY: cy - BAR_HEIGHT / 2,
    barWidth: BAR_WIDTH,
    barHeight: BAR_HEIGHT,
  };
}

/**
 * The trim edge under the pointer worth a handle: { clipId, edge } or null. Only a clip edge
 * on a track row counts, and a running drag session suppresses the hover handle (the drag's
 * own ghost takes over). Silence cuts are clip edges with an implicitRange, so they come
 * through the same path.
 */
export function hoverTrimEdge(hit, sessionActive) {
  if (sessionActive || !hit?.clip || !hit.edge || hit.row?.kind !== "track") return null;
  return { clipId: hit.clip.id, edge: hit.edge };
}

/** Same handle target? A pointer move within one edge must not repaint. */
export function sameHandle(a, b) {
  return (a?.clipId ?? null) === (b?.clipId ?? null) && (a?.edge ?? null) === (b?.edge ?? null);
}
