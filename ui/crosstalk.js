// What a transcript cut also removes (owner, 2026-10-18). A cut of selected
// words ripple-deletes the whole stretch they cover on every track of the
// edit scope (WP19a), so other speakers' words and audio inside it go too.
// The UI shows that before the key is pressed. Pure; the backend gets the
// same rule as `transcript.cut_preview` (GUI-DESIGN.md, "Crosstalk").

/**
 * `words`: timeline words [{track, start, end, text}] (index = word ref).
 * `selected`: indices of the selected words. `scope`: track ids the cut
 * applies to (the group's tracks). `rate`: frames per second (for seconds).
 * Returns null without a selection, else { range: [start, end], alsoWords:
 * indices of other tracks' words overlapping the range, tracks: [{ track,
 * words, seconds }] for every other track in scope, nothingElse }.
 */
export function cutPreview(words, selected, scope, rate = 1) {
  if (!selected?.length) return null;
  const chosen = selected.map((i) => words[i]).filter(Boolean);
  const start = Math.min(...chosen.map((word) => word.start));
  const end = Math.max(...chosen.map((word) => word.end));
  const owners = new Set(chosen.map((word) => word.track));
  const alsoWords = [];
  words.forEach((word, i) => {
    if (owners.has(word.track) || selected.includes(i)) return;
    if (word.start < end && word.end > start && scope.includes(word.track)) alsoWords.push(i);
  });
  const tracks = scope
    .filter((track) => !owners.has(track))
    .map((track) => ({
      track,
      words: alsoWords.filter((i) => words[i].track === track),
      seconds: (end - start) / rate,
    }));
  return { range: [start, end], alsoWords, tracks, nothingElse: tracks.length === 0 };
}
