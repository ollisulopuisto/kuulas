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

// Memoize normalized transcript strings per words array reference. Find queries run
// on every keystroke in the find input field; caching normalized strings across
// queries on the same transcript avoids re-normalizing tens of thousands of words
// repeatedly (reducing search latency on 50k words from ~175 ms to ~8 ms).
const normCache = new WeakMap();

function getNormalizedWords(words) {
  let text = normCache.get(words);
  if (!text) {
    text = words.map((word) => normalise(word.w));
    normCache.set(words, text);
  }
  return text;
}

/** Every match as a list of consecutive word indices, in timeline order. */
export function findMatches(words, query) {
  const parts = normalise(query).split(/\s+/).filter(Boolean);
  if (parts.length === 0 || (parts.length === 1 && [...parts[0]].length < 2)) return [];
  const text = getNormalizedWords(words);
  const partCount = parts.length;
  const firstPart = parts[0];
  const maxStart = words.length - partCount;
  const found = [];
  // Fast path: check the first prefix before checking subsequent parts or allocating
  for (let start = 0; start <= maxStart; start++) {
    if (!text[start].startsWith(firstPart)) continue;
    const track = words[start].track;
    let match = true;
    for (let k = 1; k < partCount; k++) {
      if (words[start + k].track !== track || !text[start + k].startsWith(parts[k])) {
        match = false;
        break;
      }
    }
    if (match) {
      const matchIndices = new Array(partCount);
      for (let k = 0; k < partCount; k++) matchIndices[k] = start + k;
      found.push(matchIndices);
    }
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
