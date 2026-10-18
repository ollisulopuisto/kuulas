// Status chip colours and sorting (WP51). Pure logic, no DOM.

export const DEFAULT_TONES = {
  Draft: "neutral",
  "Ready for review": "info",
  "In review": "info",
  "Needs fixes": "warn",
  Reviewed: "ok",
  Approved: "ok",
  Published: "done",
};

/**
 * Returns the tone name for a status label.
 *
 * @param {string} label
 * @param {Record<string, string>} [tones=DEFAULT_TONES]
 * @returns {string}
 */
export function statusTone(label, tones = DEFAULT_TONES) {
  if (typeof label !== "string") return "neutral";
  const trimmed = label.trim();
  if (!trimmed) return "neutral";
  const target = trimmed.toLowerCase();
  if (tones) {
    for (const [key, tone] of Object.entries(tones)) {
      if (key.trim().toLowerCase() === target) {
        return tone;
      }
    }
  }
  return "neutral";
}

/**
 * Sorts status labels by their index in order (case-insensitive).
 * Unknown labels are placed last in their original order.
 * Duplicates (case-insensitive) are kept once with the first spelling.
 *
 * @param {string[]} labels
 * @param {string[]} [order=[]]
 * @returns {string[]}
 */
export function sortStatuses(labels, order = []) {
  if (!Array.isArray(labels) || labels.length === 0) return [];

  const orderMap = new Map();
  if (Array.isArray(order)) {
    order.forEach((item, index) => {
      if (typeof item === "string") {
        const key = item.trim().toLowerCase();
        if (!orderMap.has(key)) {
          orderMap.set(key, index);
        }
      }
    });
  }

  const seen = new Set();
  const unique = [];
  for (const label of labels) {
    if (typeof label !== "string") continue;
    const key = label.trim().toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(label);
    }
  }

  const known = [];
  const unknown = [];

  for (const label of unique) {
    const key = label.trim().toLowerCase();
    if (orderMap.has(key)) {
      known.push({ label, index: orderMap.get(key) });
    } else {
      unknown.push(label);
    }
  }

  known.sort((a, b) => a.index - b.index);

  return [...known.map((k) => k.label), ...unknown];
}
