// Find in the transcript (Mod+F): the pure part. It mirrors src/kuulas/transcript_find.py
// (accent- and case-insensitive prefix match, a phrase is a run of consecutive words, never
// across tracks); both are tested against ui/tests/fixtures/find-cases.json so they cannot
// drift. It runs over the words array, never the DOM, so the virtualised list is no limit.

/** Lower-case, drop accents and punctuation; digits and spaces stay. */
export function normalise(text) {
  return text
    .normalize("NFKD")
    .replace(/[^\p{L}\p{N}\s]|\p{M}/gu, "")
    .toLowerCase();
}

/** Every match as a list of consecutive word indices, in timeline order. */
export function findMatches(words, query) {
  const parts = normalise(query).split(/\s+/).filter(Boolean);
  if (parts.length === 0 || (parts.length === 1 && [...parts[0]].length < 2)) return [];
  const text = words.map((word) => normalise(word.w));
  const found = [];
  for (let start = 0; start + parts.length <= words.length; start++) {
    const track = words[start].track;
    if (
      parts.every((part, k) => words[start + k].track === track && text[start + k].startsWith(part))
    )
      found.push(Array.from({ length: parts.length }, (_, k) => start + k));
  }
  return found;
}

/** The first match starting after `position`, wrapping around; null without matches. */
export function nextMatch(matches, position) {
  if (matches.length === 0) return null;
  return matches.find((m) => m[0] > position) ?? matches[0];
}

/** The last match starting before `position`, wrapping around; null without matches. */
export function prevMatch(matches, position) {
  if (matches.length === 0) return null;
  return [...matches].reverse().find((m) => m[0] < position) ?? matches[matches.length - 1];
}

/** Where a fresh search lands: the first match at or after the cursor word, else the first. */
export function firstFrom(matches, word) {
  if (matches.length === 0) return null;
  return matches.find((m) => m[0] >= word) ?? matches[0];
}

/** "n of m": n is 0 when no match is current. */
export function currentPosition(matches, current) {
  const at = current ? matches.findIndex((m) => m[0] === current[0]) : -1;
  return { n: at + 1, m: matches.length };
}

/** The indices of all words in all matches. */
export function matchedWords(matches) {
  return new Set(matches.flat());
}
