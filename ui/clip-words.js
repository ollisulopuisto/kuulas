// Words inside the clips on the timeline (WP69), like Hindenburg's transcript along the top
// of a clip. Pure: which words belong to a clip, whether the zoom is wide enough to read
// them, and how each word is fitted into its own pixel width. timeline.js draws the result.
//
// `words` is state.words (GET /api/words): sorted by start, in timeline frames, each with
// the track and clip that plays it, so a trimmed or moved clip already owns only its words.
// The clip bounds are checked again here because the list can be one edit behind.

import { frameToX } from "./format.js";

/**
 * Words are drawn when the average word is at least this wide on screen (px). About three
 * letters of the 10 px row font plus the gap; tune on a real session.
 */
export const WORD_MIN_AVG_PX = 28;
/** Space left between two neighbouring words (px). */
export const WORD_GAP_PX = 2;
export const ELLIPSIS = "…";

/** Mean length of a word in frames; 0 for no words. Computed once per words list. */
export function averageWordFrames(words) {
  if (!words?.length) return 0;
  let total = 0;
  for (const word of words) total += word.e - word.s;
  return total / words.length;
}

/** Whether the zoom (frames per px) shows the average word wide enough to read. */
export function wordsWideEnough(avgFrames, zoom, minPx = WORD_MIN_AVG_PX) {
  return avgFrames > 0 && zoom > 0 && avgFrames / zoom >= minPx;
}

/**
 * `text` shortened to fit `widthPx` using `measure(text) -> px`: whole when it fits, else the
 * longest start plus an ellipsis, else "" (not even an ellipsis fits: the word is skipped).
 */
export function fitWord(text, widthPx, measure) {
  if (!text || !(widthPx > 0)) return "";
  if (measure(text) <= widthPx) return text;
  if (measure(ELLIPSIS) > widthPx) return "";
  // Longest prefix whose prefix + ellipsis fits (width grows with length).
  let lo = 0;
  let hi = text.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (measure(text.slice(0, mid) + ELLIPSIS) <= widthPx) lo = mid;
    else hi = mid - 1;
  }
  return text.slice(0, lo) + ELLIPSIS;
}

/** The first index whose word starts at or after `frame` (binary search; words sorted by s). */
function firstStartingAt(words, frame) {
  let lo = 0;
  let hi = words.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (words[mid].s < frame) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/**
 * Indices (ascending) of the words of this clip that show between frames `from` and `to`.
 * `lookback`: how far before `from` a word may start and still reach into the view (the
 * longest word, in frames). Only the visible stretch is looked at.
 */
export function clipWordIndices(words, { trackId, clip, from, to, lookback = 0 }) {
  if (!words?.length) return [];
  const clipEnd = clip.start + clip.length;
  const lo = Math.max(from, clip.start);
  const hi = Math.min(to, clipEnd);
  if (hi <= lo) return [];
  const out = [];
  for (let i = firstStartingAt(words, lo - lookback); i < words.length; i++) {
    const word = words[i];
    if (word.s >= hi) break;
    if (word.e <= lo || word.track !== trackId || word.clip !== clip.id) continue;
    out.push(i);
  }
  return out;
}

/**
 * The words to draw in one clip: [{ index, text, x, w, mark }] with x and w in px, `text`
 * already fitted, `mark` "plain", "current" (the word under the play cursor, index
 * `current`) or "selected" (inside `selected` = [first, last] word index, or null).
 * A word is drawn from its own start to its own end, so two never overlap.
 */
export function layoutClipWords({
  words,
  trackId,
  clip,
  scroll,
  zoom,
  viewWidth,
  lookback,
  measure,
  current = -1,
  selected = null,
}) {
  const indices = clipWordIndices(words, {
    trackId,
    clip,
    from: scroll,
    to: scroll + viewWidth * zoom,
    lookback,
  });
  const clipEnd = clip.start + clip.length;
  const items = [];
  for (const index of indices) {
    const word = words[index];
    const x = frameToX(Math.max(word.s, clip.start), scroll, zoom);
    const w = frameToX(Math.min(word.e, clipEnd), scroll, zoom) - x;
    const text = fitWord(word.w, w - WORD_GAP_PX, measure);
    if (!text) continue;
    let mark = "plain";
    if (index === current) mark = "current";
    else if (selected && index >= selected[0] && index <= selected[1]) mark = "selected";
    items.push({ index, text, x, w: w - WORD_GAP_PX, mark });
  }
  return items;
}
