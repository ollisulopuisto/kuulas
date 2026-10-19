// Which tracks a RANGE operation acts on (WP83): cut X, copy, lift-cut, close gap, delete
// range, mute range. The range is a rectangle of time by tracks; this is its track side, as
// ONE pure function of the store's state, so every range command, the dimming and the status
// chip agree (node tests: range-scope.test.js).
//
//   - Keyboard I/O: all tracks (the default; one track is never edited by accident).
//   - A range painted with the mouse inside one lane: that lane; across lanes: those lanes
//     (`rangeTracks`, set by the range drag).
//   - Selected track headers (`trackSelection`) override: while the mode is "selected tracks
//     only" a range operation acts on those tracks alone, from the keyboard as well.
//   - `rangeMode` is "all" or "selected". Selecting a header sets "selected"; clearing the
//     track selection returns to "all"; E flips it; project open resets it to "all".
import { markedRange } from "./selection.js";

export const MODE_ALL = "all";
export const MODE_SELECTED = "selected";

const tracksOf = (state) => state?.project?.tracks ?? [];
const asSet = (value) => (value instanceof Set ? value : new Set(value ?? []));

/**
 * `{ mode, source, tracks, none, total }`: `tracks` are ids in project order; `source` is
 * "all", "lanes" (the painted range), "selected" or "none" (selected-only mode with no track
 * selected: nothing would be touched, so the operation must refuse).
 */
export function resolveScope(state) {
  const all = tracksOf(state).map((track) => track.id);
  const live = (ids) => all.filter((id) => asSet(ids).has(id));
  const total = all.length;
  const mode = state?.rangeMode === MODE_SELECTED ? MODE_SELECTED : MODE_ALL;
  if (mode === MODE_SELECTED) {
    const picked = live(state?.trackSelection);
    return picked.length > 0
      ? { mode, source: "selected", tracks: picked, none: false, total }
      : { mode, source: "none", tracks: [], none: true, total };
  }
  const lanes = live(state?.rangeTracks);
  if (lanes.length > 0) return { mode, source: "lanes", tracks: lanes, none: false, total };
  return { mode, source: "all", tracks: all, none: false, total };
}

/** The state patch for a click on a track header (`add`: Cmd+click toggles it in the selection). */
export function selectTrack(state, id, { add = false } = {}) {
  const now = asSet(state?.trackSelection);
  const next = add ? new Set(now) : new Set([id]);
  if (add) {
    if (next.has(id)) next.delete(id);
    else next.add(id);
  }
  return { trackSelection: next, rangeMode: next.size > 0 ? MODE_SELECTED : MODE_ALL };
}

/** Esc (the track selection first): nothing selected, all tracks. */
export function clearTrackSelection() {
  return { trackSelection: new Set(), rangeMode: MODE_ALL };
}

/** E: flip between all tracks and selected tracks only. */
export function toggleScopeMode(state) {
  return { rangeMode: state?.rangeMode === MODE_SELECTED ? MODE_ALL : MODE_SELECTED };
}

/** Ids of the tracks the next range operation will NOT touch: drawn dimmed (lane, header, waveform). */
export function dimmedTracks(state) {
  const scope = resolveScope(state);
  if (scope.none) return new Set();
  const touched = new Set(scope.tracks);
  return new Set(
    tracksOf(state)
      .map((track) => track.id)
      .filter((id) => !touched.has(id)),
  );
}

/**
 * What the status-bar chip says, as data: null (nothing to say: all tracks and no range),
 * `{ kind: "none" }`, or `{ kind: "range" | "mode", all, count, names, start?, end? }`
 * (`names` only when not all tracks).
 */
export function scopeChip(state) {
  const scope = resolveScope(state);
  if (scope.none) return { kind: "none" };
  const range = markedRange(state);
  const all = scope.tracks.length === scope.total;
  if (!range && scope.source === "all") return null;
  const names = all
    ? []
    : tracksOf(state)
        .filter((track) => scope.tracks.includes(track.id))
        .map((track) => track.name);
  const base = { all, count: scope.tracks.length, names };
  return range
    ? { kind: "range", start: range.start, end: range.end, ...base }
    : { kind: "mode", ...base };
}
