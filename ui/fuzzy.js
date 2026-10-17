// Fuzzy filter for the palette and the cheat sheet. Pure. The query's letters
// must appear in order (case-insensitively); the score prefers a match at the
// start, at word starts and in one run.

const WORD_START = /[\s\-_./:·…]/;

/** { score, indices } or null. An empty query matches with no indices. */
export function fuzzyMatch(query, text) {
  const needle = String(query).toLocaleLowerCase();
  const hay = String(text).toLocaleLowerCase();
  if (!needle) return { score: 0, indices: [] };
  const indices = [];
  let score = 0;
  let from = 0;
  let previous = -2;
  for (const letter of needle) {
    // Prefer a word start over the first occurrence when one is close ahead.
    let at = hay.indexOf(letter, from);
    if (at === -1) return null;
    let boundary = at;
    while (boundary !== -1 && boundary > 0 && !WORD_START.test(hay[boundary - 1])) {
      boundary = hay.indexOf(letter, boundary + 1);
    }
    if (boundary !== -1 && at !== previous + 1) at = boundary;
    indices.push(at);
    if (at === 0) score += 8;
    else if (WORD_START.test(hay[at - 1])) score += 5;
    if (at === previous + 1) score += 4;
    score -= at - from > 0 ? Math.min(at - from, 6) * 0.1 : 0;
    previous = at;
    from = at + 1;
  }
  return { score, indices };
}

/** Rank items by their text; ties keep the original order. [{ item, score, indices }] */
export function fuzzyFilter(items, query, text = (item) => item) {
  const rows = [];
  items.forEach((item, order) => {
    const match = fuzzyMatch(query, text(item));
    if (match) rows.push({ item, score: match.score, indices: match.indices, order });
  });
  rows.sort((a, b) => b.score - a.score || a.order - b.order);
  return rows.map(({ item, score, indices }) => ({ item, score, indices }));
}
