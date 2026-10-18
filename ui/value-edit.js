// Typing an exact value into a gain or pan readout (owner, 2026-10-18): double-click the number,
// type, Enter. Pure parsers: null means "not a value, keep the old one".

const DB_RANGE = { min: -60, max: 12 };

/** "-2,4", "−2.4 dB", "+3" -> dB, clamped to `range` and rounded to 0.1; null when not a number. */
export function parseDbText(text, range = DB_RANGE) {
  const cleaned = String(text ?? "")
    .trim()
    .replace(/\s*db$/i, "")
    .replace("−", "-")
    .replace(",", ".");
  if (!/^[+-]?\d+(\.\d+)?$/.test(cleaned)) return null;
  const value = Math.min(range.max, Math.max(range.min, Number(cleaned)));
  return Math.round(value * 10) / 10;
}

/**
 * "L 30", "30 R", "r20", "C", "V 10" (Finnish vasen), "O 10" (oikea), "keski", or a bare percentage
 * (negative is left) -> pan in -1..1 in whole percent; null when not a pan value.
 */
export function parsePanText(text) {
  const raw = String(text ?? "")
    .trim()
    .toLowerCase()
    .replace("−", "-")
    .replace(",", ".");
  if (raw === "c" || raw === "keski" || raw === "center" || raw === "centre") return 0;
  const clampPercent = (n) => Math.round(Math.min(100, Math.max(-100, n))) / 100;
  const bare = /^([+-]?\d+(\.\d+)?)$/.exec(raw);
  if (bare) return clampPercent(Number(bare[1]));
  const sided = /^(?:([lrvo])\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*([lrvo]))$/.exec(raw);
  if (!sided) return null;
  const side = sided[1] ?? sided[4];
  const amount = Number(sided[2] ?? sided[3]);
  return clampPercent(side === "l" || side === "v" ? -amount : amount);
}
