// Tab and Shift+Tab (WP19i, Pro Tools "Tab to transient"): the playhead jumps to the next
// or previous stop of the current SCOPE. A scope says what a stop is: a word start, a clip
// border or a sound (transient). Pure functions; app.js fetches the edges and transients.

/** The scopes, in the order the cycle key steps through them. */
export const TAB_SCOPES = ["word", "edge", "sound"];

/** The edit_points mode (src/kuulas/edit_points.py) each server-side scope asks for. */
export const SCOPE_MODE = { edge: "edges", sound: "transients" };

/** Remembered choices from the old word/transient/both cycle. */
const LEGACY_SCOPE = { transient: "sound", both: "word" };

/** The next scope after `scope`; an unknown one starts at the first. */
export function cycleScope(scope) {
  const at = TAB_SCOPES.indexOf(scope);
  return TAB_SCOPES[(at + 1) % TAB_SCOPES.length];
}

/**
 * Tab goes to the next seam (clip border) on any track by default (owner, 2026-10-18: it is hard to
 * tell which channel is active). Words and sounds are one Alt+Tab away.
 */
export const defaultScope = () => "edge";

/** A remembered scope if valid (old values migrate: transient to sound, both to word), else the default. */
export function scopeChoice(stored, hasTranscript) {
  if (TAB_SCOPES.includes(stored)) return stored;
  return LEGACY_SCOPE[stored] ?? defaultScope(hasTranscript);
}

/** The catalog key of the indicator text for a scope ("Tab: words"). */
export const scopeIndicatorKey = (scope) => `ui.tab_scope.indicator.${scope}`;

/**
 * Are the words in `state` the ones of the edit the user is looking at? They are derived
 * from the edit, so after any change of head they are stale until fetched again.
 */
export const wordsAreCurrent = (state) =>
  state?.head != null && state.wordsHead === state.head && Array.isArray(state.words);

/** The first stop strictly after `frame` in the sorted `stops`; null at the end. */
export function nextStop(stops, frame) {
  const list = stops ?? [];
  let lo = 0;
  let hi = list.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (list[mid] <= frame) lo = mid + 1;
    else hi = mid;
  }
  return lo < list.length ? list[lo] : null;
}

/** The last stop strictly before `frame` in the sorted `stops`; null at the start. */
export function prevStop(stops, frame) {
  const list = stops ?? [];
  let lo = 0;
  let hi = list.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (list[mid] < frame) lo = mid + 1;
    else hi = mid;
  }
  return lo > 0 ? list[lo - 1] : null;
}

/** Several lists of frames as one sorted list without duplicates. */
export function mergeStops(...lists) {
  const all = new Set();
  for (const list of lists) for (const frame of list ?? []) all.add(frame);
  return [...all].sort((a, b) => a - b);
}

/** Start frames of the transcript words (state.words), muted ones left out, sorted. */
export function wordStops(words, trackId = null) {
  return mergeStops(
    (words ?? [])
      .filter((word) => !word.muted && (trackId === null || word.track === trackId))
      .map((word) => word.s),
  );
}

/**
 * The stops of a scope. `words` are the transcript words, `server` the stops the server
 * gave for the scope (edges or transients), `markers` the project's markers and regions,
 * which are stops in every scope. Word stops are the focused track's; a track
 * without words (music) falls back to all words.
 */
export function stopsForScope(scope, { words = [], track = null, server = [], markers = [] } = {}) {
  const marked = markerStops(markers);
  if (scope === "word") {
    const own = wordStops(words, track);
    return mergeStops(own.length > 0 || track === null ? own : wordStops(words), marked);
  }
  return mergeStops(server, marked);
}

/** The frames of the markers (a region gives its start and its end): Tab stops in every scope. */
export function markerStops(markers) {
  return mergeStops(
    (markers ?? []).flatMap((marker) => [marker.start, marker.end].filter(Number.isFinite)),
  );
}

/**
 * The patch for a click on or focus in a track or bus header: that is the timeline's
 * keyboard context. Without it the panel stayed whatever it was (transcript, inspector),
 * the context stayed "side", and Tab and the arrow keys did not reach the timeline's keys.
 */
export const headerFocusPatch = (state) =>
  state?.panel === "timeline" ? null : { panel: "timeline" };
