// Tab and Shift+Tab (WP19i, Pro Tools "Tab to transient"): the playhead jumps to the
// next or previous stop. What a stop is depends on the target mode: word starts,
// transients, or both. Pure functions; app.js fetches the transients.

/** The modes, in the order the cycle key steps through them. */
export const TAB_TARGETS = ["word", "transient", "both"];

/** The next mode after `mode`; an unknown one starts at the first. */
export function cycleTarget(mode) {
  const at = TAB_TARGETS.indexOf(mode);
  return TAB_TARGETS[(at + 1) % TAB_TARGETS.length];
}

/** Word stops need a transcript; without one the transients are all there is. */
export const defaultTarget = (hasTranscript) => (hasTranscript ? "word" : "transient");

/** A remembered mode if it is one of the three, else the default. */
export function targetChoice(stored, hasTranscript) {
  return TAB_TARGETS.includes(stored) ? stored : defaultTarget(hasTranscript);
}

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
