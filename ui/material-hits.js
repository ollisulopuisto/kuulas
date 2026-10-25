// The find bar's "Not in this edit" list (pure): the reason tag of a hit and what can be
// done with it. GET /api/material-search gives the hits (src/kuulas/material_search.py);
// transcript.js draws them.

const KEYS = {
  cut: "ui.find.removed.cut",
  muted: "ui.find.removed.muted",
  gated: "ui.find.removed.gated",
  unused: "ui.find.removed.unused",
};

/** The message key of a reason tag: CUT, MUTED, GATED or UNUSED (an unknown one reads as cut). */
export const statusKey = (status) => KEYS[status] ?? KEYS.cut;

/** Muted and gated words are still on the timeline: the hit then carries where (`at`). */
export const canShow = (hit) => typeof hit.at === "number";

/** The line that opens the list, or null when nothing outside the edit matches. */
export const removedSummary = (count) =>
  count > 0 ? { key: "ui.find.removed.summary", values: { count } } : null;
