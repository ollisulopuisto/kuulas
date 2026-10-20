// Fuzzy matching of a typed plug-in name against the installed plug-ins (GET /api/plugins).
// Pure. The same rule as src/kuulas/plugins.py (`match`); keep them in step, the tests of
// both use the same table. Case, spaces and punctuation are ignored; exact beats prefix
// beats word-prefix beats subsequence beats a one-edit typo; one entry per name (VST3
// over AU over VST2).

export const FORMAT_RANK = { VST3: 0, AU: 1, VST2: 2 };
export const TIERS = ["exact", "prefix", "word", "subsequence", "typo"];
export const DEFAULT_LIMIT = 8;
// A typo is only tolerated for a name and a query this long (shorter ones match nearly
// everything).
const TYPO_MIN_NAME = 5;
const TYPO_MIN_QUERY = 4;

const isAlnum = (ch) => /[\p{L}\p{N}]/u.test(ch);

/** { compact, origin, starts }: the letters and digits lowercased and joined, the index in
 * `text` of each (in UTF-16 units), and the compact index each word starts at. */
function chars(text) {
  const compact = [];
  const origin = [];
  const starts = [];
  let inside = false;
  let i = 0;
  for (const ch of String(text)) {
    if (isAlnum(ch)) {
      if (!inside) starts.push(compact.length);
      inside = true;
      compact.push(ch.toLowerCase());
      origin.push(i);
    } else {
      inside = false;
    }
    i += ch.length;
  }
  return { compact: compact.join(""), origin, starts };
}

/** Damerau-Levenshtein (optimal string alignment): insert, delete, replace, swap. */
export function editDistance(a, b) {
  let prev2 = [];
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      row[j] = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
        row[j] = Math.min(row[j], prev2[j - 2] + 1);
      }
    }
    prev2 = prev;
    prev = row;
  }
  return prev[b.length];
}

const range = (from, n) => Array.from({ length: n }, (_, k) => from + k);

function tierOf(q, compact, starts) {
  const n = q.length;
  if (compact === q) return { tier: "exact", picked: range(0, n) };
  if (compact.startsWith(q)) return { tier: "prefix", picked: range(0, n) };
  for (const s of starts) {
    if (compact.startsWith(q, s)) return { tier: "word", picked: range(s, n) };
  }
  let at = 0;
  const picked = [];
  for (const ch of q) {
    at = compact.indexOf(ch, at);
    if (at < 0) break;
    picked.push(at);
    at += 1;
  }
  if (picked.length === n) return { tier: "subsequence", picked };
  if (compact.length >= TYPO_MIN_NAME && n >= TYPO_MIN_QUERY) {
    for (const s of [0, ...starts]) {
      for (const size of [n - 1, n, n + 1]) {
        if (editDistance(q, compact.slice(s, s + size)) <= 1) return { tier: "typo", picked: [] };
      }
    }
  }
  return null;
}

/**
 * The best `limit` of `items` ({ name, format, path }) for `query`: the item plus `tier`
 * and `indices` (positions in the name to highlight). Empty query: nothing.
 */
export function matchPlugins(query, items, limit = DEFAULT_LIMIT) {
  const q = chars(query).compact;
  if (!q) return [];
  const best = new Map();
  for (const item of items) {
    const key = chars(item.name).compact;
    const old = best.get(key);
    if (!old || (FORMAT_RANK[item.format] ?? 9) < (FORMAT_RANK[old.format] ?? 9)) {
      best.set(key, item);
    }
  }
  const rows = [];
  for (const [key, item] of best) {
    const { compact, origin, starts } = chars(item.name);
    const hit = tierOf(q, compact, starts);
    if (!hit) continue;
    rows.push({
      rank: TIERS.indexOf(hit.tier),
      size: key.length,
      lower: item.name.toLowerCase(),
      row: { ...item, tier: hit.tier, indices: hit.picked.map((i) => origin[i]) },
    });
  }
  rows.sort(
    (a, b) =>
      a.rank - b.rank || a.size - b.size || (a.lower < b.lower ? -1 : a.lower > b.lower ? 1 : 0),
  );
  return rows.slice(0, limit).map((r) => r.row);
}

/** Free text that names a file rather than a plug-in: it has a path separator. */
export const looksLikePath = (text) => /[/\\]/.test(text) || text.startsWith("~");

/**
 * What a typed text stands for: { kind: "empty" } | { kind: "path", path } (free text with
 * a separator, taken as typed) | { kind: "plain", text } (nothing is installed or the scan
 * failed: the field is plain text) | { kind: "match", plugin } (the best match) |
 * { kind: "none" } (a name no installed plug-in matches).
 */
export function resolveTyped(text, installed) {
  const typed = String(text ?? "").trim();
  if (!typed) return { kind: "empty" };
  if (looksLikePath(typed)) return { kind: "path", path: typed };
  if (installed.length === 0) return { kind: "plain", text: typed };
  const [best] = matchPlugins(typed, installed, 1);
  return best ? { kind: "match", plugin: best } : { kind: "none" };
}

/** The last path component without its extension: the chip's text for a typed path. */
export function pathLabel(path) {
  const parts = String(path).split(/[/\\]/).filter(Boolean);
  const last = parts.at(-1) ?? String(path);
  return last.replace(/\.(vst3|component|vst|so|dll)$/i, "");
}

/** The name to show for a stored value: the installed plug-in with that path, else the
 * path's own name. */
export function labelFor(path, installed) {
  return installed.find((p) => p.path === path)?.name ?? pathLabel(path);
}

/** Split `name` into [{ text, hit }] runs for highlighting the `indices` of a match. */
export function highlightRuns(name, indices) {
  const marked = new Set(indices);
  const runs = [];
  let at = 0;
  for (const ch of name) {
    const hit = marked.has(at);
    const last = runs.at(-1);
    if (last && last.hit === hit) last.text += ch;
    else runs.push({ text: ch, hit });
    at += ch.length;
  }
  return runs;
}
