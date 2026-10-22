// The side-panel tab strip never wraps (owner, 2026-10-21). Steps, roomiest first:
//   full    - every label, normal padding
//   tight   - every label, less padding
//   compact - the selected tab keeps its label and key; the others show an icon plus their key
//   minimal - as compact, but the selected tab shows only its label (the last thing to give)
// A bare digit means nothing (owner, 2026-10-22: "Tarkastin 1 2 3 4 5"), so the key is always
// the whole shown combo, "⌥1" on mac and "Alt+1" elsewhere, at every step.
// The browser measures how wide the strip needs to be in `full`, `tight` and `compact`; this picks.

/** The step for `available` px, given the measured widths `needed` = { full, tight, compact }. */
export function tabMode(needed, available) {
  if (needed.full <= available) return "full";
  if (needed.tight <= available) return "tight";
  if (needed.compact <= available) return "compact";
  return "minimal";
}

/** Tooltip: the tab's name and its keys, "History (Alt+5)". */
export const tabTitle = (name, combos) =>
  combos.length > 0 ? `${name} (${combos.join(", ")})` : name;

/** The key shown on the tab: the first shown combo whole, modifier included ("" if unbound). */
export const tabHint = (shown) => shown[0] ?? "";
