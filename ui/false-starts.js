/**
 * Finds false starts in an array of transcript words.
 *
 * A false start is a speaker beginning a phrase, stopping, and beginning
 * the same phrase again.
 */

function cleanWord(text) {
  return text.toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
}

export function findFalseStarts(words, { minWords = 2, maxGap = 48000 } = {}) {
  if (typeof minWords !== "number" || !Number.isFinite(minWords) || minWords < 1) {
    throw new Error("minWords must be >= 1");
  }
  if (typeof maxGap !== "number" || !Number.isFinite(maxGap) || maxGap < 0) {
    throw new Error("maxGap must be >= 0");
  }
  if (!words) return [];

  for (let idx = 0; idx < words.length; idx++) {
    const w = words[idx];
    if (
      !w ||
      typeof w.text !== "string" ||
      typeof w.s !== "number" ||
      !Number.isFinite(w.s) ||
      typeof w.e !== "number" ||
      !Number.isFinite(w.e)
    ) {
      throw new Error(`Word at index ${idx} is missing text, s or e`);
    }
  }

  const cleaned = words.map((w) => cleanWord(w.text));
  const hits = [];
  let lastEndIndex = -1;

  for (let i = 0; i < words.length; i++) {
    if (i <= lastEndIndex) continue;
    if (cleaned[i] === "") continue;

    let bestMatch = null;
    const maxPossibleN = Math.floor((words.length - i) / 2);

    for (let n = minWords; n <= maxPossibleN; n++) {
      const maxJ = Math.min(words.length - n, i + n + 3);
      for (let j = i + n; j <= maxJ; j++) {
        if (words[j].s - words[j - 1].e > maxGap) continue;

        let matches = true;
        for (let k = 0; k < n; k++) {
          const wI = cleaned[i + k];
          const wJ = cleaned[j + k];
          if (wI === "" || wI !== wJ) {
            matches = false;
            break;
          }
        }

        if (matches) {
          if (!bestMatch || n > bestMatch.n) {
            bestMatch = { n, j };
          }
        }
      }
    }

    if (bestMatch) {
      hits.push({
        index: i,
        count: bestMatch.j - i,
        s: words[i].s,
        e: words[bestMatch.j - 1].e,
        repeatIndex: bestMatch.j,
      });
      lastEndIndex = bestMatch.j - 1;
    }
  }

  return hits;
}
