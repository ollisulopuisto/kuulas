// The side-panel tab strip never wraps (owner, 2026-10-21). Steps, roomiest first:
//   full    - every label, normal padding
//   tight   - every label, less padding
//   compact - only the selected tab keeps its label; the others show their key digit
// The browser measures how wide the strip needs to be in `full` and `tight`; this picks.

/** The step for `available` px, given the measured widths `needed` = { full, tight }. */
export function tabMode(needed, available) {
  if (needed.full <= available) return "full";
  if (needed.tight <= available) return "tight";
  return "compact";
}

/** Tooltip: the tab's name and its keys, "History (Alt+5)". */
export const tabTitle = (name, combos) =>
  combos.length > 0 ? `${name} (${combos.join(", ")})` : name;

/** The short form of a shown key for the compact step: "Alt+3" or "⌥3" -> "3". */
export function keyHint(shown) {
  if (!shown) return "";
  return shown.replace(/^.*\+(?=.)/, "").replace(/^[^\p{L}\p{N}]+(?=.)/u, "");
}
