/**
 * Highlights matched words from a search query in a text string.
 *
 * Normalizes case and accents while accurately tracking character spans
 * in the original string.
 */

function normalize(str) {
  return str.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "");
}

function buildNormMap(text) {
  let norm = "";
  const map = [];
  let origIdx = 0;

  for (const ch of text) {
    const normCh = normalize(ch);
    for (let k = 0; k < normCh.length; k++) {
      map.push({ start: origIdx, end: origIdx + ch.length });
    }
    origIdx += ch.length;
    norm += normCh;
  }

  return { norm, map };
}

export function highlightSegments(text, query) {
  if (typeof text !== "string" || text.length === 0) {
    return [];
  }

  const rawQuery = typeof query === "string" ? query : "";
  const queryWords = rawQuery.trim().split(/\s+/).filter(Boolean);

  if (queryWords.length === 0) {
    return [{ text, match: false }];
  }

  const { norm, map } = buildNormMap(text);
  if (norm.length === 0) {
    return [{ text, match: false }];
  }

  const spans = [];

  for (const word of queryWords) {
    const normWord = normalize(word);
    if (normWord.length === 0) continue;

    let pos = 0;
    while (pos <= norm.length - normWord.length) {
      const idx = norm.indexOf(normWord, pos);
      if (idx === -1) break;

      const startNorm = idx;
      const endNorm = idx + normWord.length;

      if (startNorm < map.length && endNorm - 1 < map.length) {
        const origStart = map[startNorm].start;
        const origEnd = map[endNorm - 1].end;
        spans.push([origStart, origEnd]);
      }

      pos = idx + 1;
    }
  }

  if (spans.length === 0) {
    return [{ text, match: false }];
  }

  spans.sort((a, b) => a[0] - b[0] || a[1] - b[1]);

  const merged = [];
  for (const span of spans) {
    if (merged.length === 0) {
      merged.push([...span]);
    } else {
      const last = merged[merged.length - 1];
      if (span[0] <= last[1]) {
        last[1] = Math.max(last[1], span[1]);
      } else {
        merged.push([...span]);
      }
    }
  }

  const segments = [];
  let cursor = 0;

  for (const [start, end] of merged) {
    if (start > cursor) {
      segments.push({ text: text.slice(cursor, start), match: false });
    }
    segments.push({ text: text.slice(start, end), match: true });
    cursor = end;
  }

  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), match: false });
  }

  return segments;
}
