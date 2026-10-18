// Lane sizing: fit the lanes to the window, drag one lane's height, decide when
// auto-fit runs. Pure (no DOM); app.js and tracks.js do the pointer and layout work.
import { fitLaneHeights } from "./lane-fit.js";
import { clampLaneHeight, layoutRows, MAX_LANE, MIN_LANE } from "./lanes.js";

const hasOwn = (heights, id) => Number.isFinite(heights?.[id]);

/**
 * The global lane height at which every lane fits `available` px (the lane area
 * below the ruler), or null when there is nothing to fit: no project or tracks,
 * no measured room, or every lane has a height of its own. Bus rows and group
 * gaps are fixed and come off first, and so do lanes sized by hand; the rest
 * share what is left (fitLaneHeights), rounded down so nothing overflows.
 * Collapsed buses (`collapsed`, a Set of bus ids) have no member lanes: only their
 * row counts.
 */
export function fitHeight({
  project,
  available,
  busHeight,
  groupGap,
  laneHeights = {},
  collapsed,
}) {
  if (!project || !(available > 0)) return null;
  const layout = layoutRows(project, MIN_LANE, {
    busHeight,
    groupGap,
    mergeSingle: true,
    laneHeights,
    collapsed,
  });
  const free = layout.rows.filter((row) => row.kind === "track" && !hasOwn(laneHeights, row.id));
  if (free.length === 0) return null;
  const fixed = layout.height - free.reduce((sum, row) => sum + row.height, 0);
  const { heights } = fitLaneHeights({
    available: available - fixed,
    tracks: free.map((row) => ({ id: row.id })),
    min: MIN_LANE,
    max: MAX_LANE,
  });
  return clampLaneHeight(Math.min(...Object.values(heights)));
}

/** A lane's height while its border is dragged: where it began, plus the pointer's travel. */
export function dragLaneHeight({ startHeight, startY, y }) {
  const travel = y - startY;
  if (!Number.isFinite(travel)) return clampLaneHeight(startHeight);
  return clampLaneHeight(startHeight + travel);
}

/** A copy of the per-lane heights with one lane set (clamped) or, with null, reset. */
export function withLaneHeight(heights, id, height) {
  const next = { ...heights };
  if (height === null) delete next[id];
  else next[id] = clampLaneHeight(height);
  return next;
}

/** The heights of tracks that still exist. */
export function pruneLaneHeights(heights, project) {
  const ids = new Set((project?.tracks ?? []).map((track) => track.id));
  return Object.fromEntries(Object.entries(heights ?? {}).filter(([id]) => ids.has(id)));
}

/**
 * Everything that moves the lanes, as a string: the lane area, which tracks are on
 * which bus, the bus and gap sizes, the lanes sized by hand. "" when there is
 * nothing to fit (no project, no measured room). Clips, names and levels are not in
 * it, so editing audio never refits.
 */
export function autoFitKey({ project, available, busHeight, groupGap, laneHeights, collapsed }) {
  if (!project || !(available > 0)) return "";
  return JSON.stringify([
    available,
    project.tracks.map((track) => [track.id, track.bus ?? ""]),
    (project.buses ?? []).map((bus) => bus.id),
    busHeight,
    groupGap,
    laneHeights ?? {},
    [...(collapsed ?? [])],
  ]);
}

/** Auto-fit runs when it is on and the key differs from the one it last fitted for. */
export function shouldAutoFit({ on, key, last }) {
  return Boolean(on) && key !== "" && key !== last;
}
