// Narration placeholders (WP43): the pure helpers behind the lane drawing, the hit
// test and the text editor. A placeholder is script text on a track with an estimated
// length, to be recorded or imported later in place (docs/FORMAT.md, "WP43").

/** Mirrors narration.py: about 2.3 words a second, at least one second for any text. */
export const WORDS_PER_SECOND = 2.3;
/** A placeholder narrower than this (px) shows no text, only its dashed outline. */
export const MIN_TEXT_PX = 24;
const WORD = /[\p{L}\p{N}_]+(?:[-'’.,][\p{L}\p{N}_]+)*/gu;

export function countWords(text) {
  return (String(text ?? "").match(WORD) ?? []).length;
}

/** The length the server will estimate for `text` (narration.estimate_frames), in frames. */
export function estimateFrames(text, rate, wordsPerSecond = WORDS_PER_SECOND) {
  const words = countWords(text);
  if (words === 0) return 0;
  return Math.max(Math.ceil((words / wordsPerSecond) * rate), rate);
}

/** Whole seconds for "about 6 s". */
export function aboutSeconds(frames, rate) {
  return Math.max(1, Math.round(frames / rate));
}

/** What the editor shows under the text while typing: { words, seconds } (seconds 0 for none). */
export function estimatePreview(text, rate) {
  const frames = estimateFrames(text, rate);
  return { words: countWords(text), seconds: frames === 0 ? 0 : aboutSeconds(frames, rate) };
}

/** The placeholder on `trackId` under timeline `frame` (the later one where two overlap). */
export function placeholderAt(placeholders, trackId, frame) {
  let found = null;
  for (const h of placeholders ?? []) {
    if (h.track === trackId && frame >= h.start && frame < h.start + h.length) found = h;
  }
  return found;
}

/** The selected placeholder, or null. */
export function selectedPlaceholder(state) {
  const id = state?.placeholderSelected;
  return id ? ((state.project?.placeholders ?? []).find((h) => h.id === id) ?? null) : null;
}

/** Where `T` puts a new placeholder: the current track, else the first. -> track id or null. */
export function targetTrack(state) {
  const tracks = state?.project?.tracks ?? [];
  if (tracks.some((track) => track.id === state?.focusTrack)) return state.focusTrack;
  return tracks[0]?.id ?? null;
}

/** The text cut to `maxWidth` with an ellipsis; `measure(text)` gives pixels. */
export function fitText(text, maxWidth, measure) {
  if (maxWidth <= 0) return "";
  if (measure(text) <= maxWidth) return text;
  let low = 0;
  let high = text.length;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (measure(`${text.slice(0, mid)}…`) <= maxWidth) low = mid;
    else high = mid - 1;
  }
  return low === 0 ? "" : `${text.slice(0, low).trimEnd()}…`;
}

/**
 * What to write inside a placeholder `width` px wide: the script text in quotes, clipped, and
 * the estimate ("about 6 s", already translated by the caller as `estimate`) after it when
 * both fit. -> { script, estimate } with "" for what does not fit.
 */
export function placeholderLabel({ text, estimate, width, measure }) {
  const room = width - 2 * 6;
  if (room < MIN_TEXT_PX) return { script: "", estimate: "" };
  const quoted = `“${text}”`;
  const tail = estimate ? `  ${estimate}` : "";
  if (tail && measure(quoted) + measure(tail) <= room) return { script: quoted, estimate: tail };
  return { script: fitText(quoted, room, measure), estimate: "" };
}

/** A fresh id; the server accepts any unused one. */
export function newPlaceholderId(random = Math.random) {
  return `h${random().toString(16).slice(2, 12).padEnd(10, "0")}`;
}
