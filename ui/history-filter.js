/**
 * History list filtering and highlight segmentation (T65).
 */

export function filterSteps(steps, query) {
  if (!query || typeof query !== "string" || !query.trim()) {
    return steps;
  }

  const words = query.trim().toLocaleLowerCase("fi").split(/\s+/).filter(Boolean);

  if (words.length === 0) {
    return steps;
  }

  return steps.filter((step) => {
    const label = String(step?.label || "").toLocaleLowerCase("fi");
    return words.every((word) => label.includes(word));
  });
}

export function highlight(label, query) {
  const text = String(label ?? "");
  if (!query || typeof query !== "string" || !query.trim()) {
    return [{ text, match: false }];
  }

  const words = query.trim().toLocaleLowerCase("fi").split(/\s+/).filter(Boolean);

  if (words.length === 0) {
    return [{ text, match: false }];
  }

  const lower = text.toLocaleLowerCase("fi");
  const ranges = [];

  for (const word of words) {
    let pos = 0;
    while (pos < lower.length) {
      const idx = lower.indexOf(word, pos);
      if (idx === -1) {
        break;
      }
      ranges.push([idx, idx + word.length]);
      pos = idx + 1;
    }
  }

  if (ranges.length === 0) {
    return [{ text, match: false }];
  }

  ranges.sort((a, b) => a[0] - b[0] || a[1] - b[1]);

  const merged = [];
  for (const [start, end] of ranges) {
    if (merged.length === 0) {
      merged.push([start, end]);
    } else {
      const last = merged[merged.length - 1];
      if (start <= last[1]) {
        last[1] = Math.max(last[1], end);
      } else {
        merged.push([start, end]);
      }
    }
  }

  const segments = [];
  let curr = 0;
  for (const [start, end] of merged) {
    if (start > curr) {
      segments.push({ text: text.slice(curr, start), match: false });
    }
    segments.push({ text: text.slice(start, end), match: true });
    curr = end;
  }

  if (curr < text.length) {
    segments.push({ text: text.slice(curr), match: false });
  }

  return segments;
}
