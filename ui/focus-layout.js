/**
 * Pure logic and state management for focus mode lane layout (WP28, docs/design/FOCUS-MODE.md).
 * Focus changes what you see; solo changes what you hear. The heights here are a view layer:
 * never written to laneHeights, never in history or the project file.
 */
import { layoutRows, MAX_LANE, MIN_LANE } from "./lanes.js";
import { cueFor } from "./motion.js";
import { dimmedTracks } from "./range-scope.js";

/** A lane out of focus: its name, half a waveform and its clip edges, so sync stays visible. */
export const FOCUS_STRIP = 16;
/** The room the lanes out of focus share (owner, 2026-10-23: 16 px strips were "a BIT too
 *  extreme", the other tracks must still be seen), and the most one of them takes. */
export const FOCUS_SIDE_SHARE = 0.4;
export const FOCUS_SIDE_MAX = 64;

/** How tall each lane out of focus is when `others` of them share `room` px. */
export function sideHeight(room, others) {
  if (!(others > 0)) return FOCUS_STRIP;
  const share = Math.floor((FOCUS_SIDE_SHARE * room) / others);
  return Math.max(FOCUS_STRIP, Math.min(FOCUS_SIDE_MAX, share));
}

export function focusSet(tracks, trackId) {
  if (!tracks || !trackId) return [];
  const target = tracks.find((t) => t.id === trackId);
  if (!target) return [];
  const speaker = target.speaker ? target.speaker.trim() : "";
  if (speaker) {
    return tracks.filter((t) => (t.speaker ? t.speaker.trim() : "") === speaker).map((t) => t.id);
  }
  return [trackId];
}

export function focusLayout(tracks, focusIds, options = {}) {
  const { available = 0, strip = 16, min = 28, max = 400 } = options;
  if (!tracks || tracks.length === 0) {
    return { heights: {}, total: 0 };
  }

  const focusSetIds = new Set(focusIds || []);
  const focusedTracks = tracks.filter((t) => focusSetIds.has(t.id));
  const nonFocusedTracks = tracks.filter((t) => !focusSetIds.has(t.id));

  if (focusedTracks.length === 0) {
    const h = Math.max(min, Math.min(max, Math.floor(available / tracks.length)));
    const heights = {};
    let total = 0;
    for (const t of tracks) {
      heights[t.id] = h;
      total += h;
    }
    return { heights, total };
  }

  const heights = {};
  for (const t of nonFocusedTracks) {
    heights[t.id] = strip;
  }

  const nonFocusedTotal = nonFocusedTracks.length * strip;
  const spaceForFocused = available - nonFocusedTotal;

  const base = Math.floor(spaceForFocused / focusedTracks.length);
  const rem = spaceForFocused % focusedTracks.length;

  for (let i = 0; i < focusedTracks.length; i++) {
    const allocated = base + (i < rem ? 1 : 0);
    heights[focusedTracks[i].id] = Math.max(min, Math.min(max, allocated));
  }

  let total = 0;
  for (const t of tracks) {
    total += heights[t.id];
  }

  return { heights, total };
}

export function walkFocus(tracks, focusIds, direction) {
  if (!tracks || tracks.length === 0 || !focusIds || focusIds.length === 0) {
    return focusIds || [];
  }
  const focusSetIds = new Set(focusIds);
  const matchingIndices = [];
  for (let i = 0; i < tracks.length; i++) {
    if (focusSetIds.has(tracks[i].id)) {
      matchingIndices.push(i);
    }
  }
  if (matchingIndices.length === 0) {
    return focusIds;
  }
  if (direction === 1) {
    const lastIdx = Math.max(...matchingIndices);
    if (lastIdx + 1 < tracks.length) {
      return focusSet(tracks, tracks[lastIdx + 1].id);
    }
    return focusIds;
  }
  if (direction === -1) {
    const firstIdx = Math.min(...matchingIndices);
    if (firstIdx - 1 >= 0) {
      return focusSet(tracks, tracks[firstIdx - 1].id);
    }
    return focusIds;
  }
  return focusIds;
}

export function enterFocus(state, trackId, tracks, soloSet) {
  const newFocus = focusSet(tracks, trackId);
  const soloBefore = soloSet ? [...soloSet] : (state?.soloBefore ?? null);
  return {
    focus: newFocus,
    soloBefore,
  };
}

export function leaveFocus(state) {
  return {
    state: { focus: null, soloBefore: null },
    restoreSolo: state?.soloBefore ?? null,
  };
}

/**
 * The view-layer heights of the lanes in focus mode, { trackId: px } for every track that has a
 * row, or null when there is nothing to do (no project, no measured room, or no focused track
 * with a row: a focused track folded into a collapsed bus is not unfolded). Bus rows and group
 * gaps keep their height and come off first; the other lanes become strips; the focused lanes
 * share the rest within the lane limits (MIN_LANE..MAX_LANE, so a tall window can leave room
 * below the last lane).
 */
export function focusHeights({
  project,
  focusIds,
  available,
  busHeight,
  groupGap,
  collapsed,
  strip = null,
}) {
  if (!project || !(available > 0) || !focusIds?.length) return null;
  const layout = layoutRows(project, MIN_LANE, {
    busHeight,
    groupGap,
    mergeSingle: true,
    collapsed,
  });
  const lanes = layout.rows.filter((row) => row.kind === "track");
  const wanted = new Set(focusIds);
  if (!lanes.some((row) => wanted.has(row.id))) return null;
  const fixed = layout.rows
    .filter((row) => row.kind !== "track")
    .reduce((total, row) => total + row.height, 0);
  const room = available - fixed;
  const others = lanes.filter((row) => !wanted.has(row.id)).length;
  return focusLayout(
    lanes.map((row) => ({ id: row.id })),
    focusIds,
    { available: room, strip: strip ?? sideHeight(room, others), min: MIN_LANE, max: MAX_LANE },
  ).heights;
}

/**
 * Heights part way from `from` to `to` (t in 0..1, eased out like --ease-standard), in whole
 * pixels; at t >= 1 exactly `to`. A lane missing from `from` starts at its target.
 */
export function tweenHeights(from, to, t) {
  const done = !(t < 1);
  const eased = done ? 1 : 1 - (1 - Math.max(0, t)) ** 3;
  const out = {};
  for (const [id, end] of Object.entries(to ?? {})) {
    const start = Number.isFinite(from?.[id]) ? from[id] : end;
    out[id] = done ? end : Math.round(start + (end - start) * eased);
  }
  return out;
}

/**
 * How long the lanes take to reach their focus heights, in ms; 0 jumps. The motion setting
 * decides (motion.js "focus-resize": 120 ms, shorter at subtle, none when off or under reduced
 * motion), and nothing animates while playing (GUI-DESIGN.md section 20).
 */
export function focusResizeMs(mode, { playing = false } = {}) {
  const cue = cueFor("focus-resize", mode, { playing });
  return cue.animate ? cue.ms : 0;
}

/** The tracks drawn as inactive in focus mode: every track not in focus. */
export function outOfFocus(project, focusIds) {
  if (!focusIds?.length) return new Set();
  const wanted = new Set(focusIds);
  return new Set((project?.tracks ?? []).map((track) => track.id).filter((id) => !wanted.has(id)));
}

/**
 * Every lane drawn with the inactive look (silence-visuals.js inactiveLook): the tracks the
 * next range operation will not touch (range-scope.js) and, in focus mode, the tracks out of
 * focus. One set, so the waveform layer, the overlay and the headers agree.
 */
export function inactiveTracks(state) {
  const out = dimmedTracks(state);
  for (const id of outOfFocus(state?.project, state?.focusMode?.ids)) out.add(id);
  return out;
}

/**
 * Enter focus mode on the current track: { ids, soloBefore }, or null with no current track.
 * With `solo` (focus and solo) the solo set as it is now is remembered for leaving.
 */
export function startFocus(tracks, current, { solo = false } = {}) {
  const ids = focusSet(tracks, current);
  if (ids.length === 0) return null;
  const soloed = solo
    ? (tracks ?? []).filter((track) => track.solo).map((track) => track.id)
    : null;
  const entered = enterFocus(null, current, tracks, soloed);
  return { ids: entered.focus, soloBefore: entered.soloBefore };
}

/** Leave focus mode: the solo set to restore, or null when focus did not touch solo. */
export function stopFocus(mode) {
  return { restoreSolo: leaveFocus(mode).restoreSolo };
}

/** Up/Down while focused: the next or previous speaker's tracks; the same mode at the ends. */
export function stepFocusMode(tracks, mode, direction) {
  const ids = walkFocus(tracks, mode.ids, direction);
  if (ids === mode.ids || ids.join() === mode.ids.join()) return mode;
  return { ...mode, ids };
}

/** The focus after another track became current (a click on a strip): that track's speaker. */
export function followCurrent(tracks, focusIds, current) {
  if (!current || focusIds.includes(current)) return focusIds;
  const ids = focusSet(tracks, current);
  return ids.length > 0 ? ids : focusIds;
}

/**
 * The additive solo toggles (ops.solo, exclusive false) that turn the tracks' solo set into
 * `target`, in track order. The server merges solo clicks into one undo step.
 */
export function soloSteps(tracks, target) {
  const wanted = new Set(target ?? []);
  return (tracks ?? [])
    .filter((track) => Boolean(track.solo) !== wanted.has(track.id))
    .map((track) => track.id);
}
