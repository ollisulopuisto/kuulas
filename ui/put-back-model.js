// Put back (pure): what the preview under the find bar says and what the command sends.
// POST /api/put-back/plan gives the plan (src/kuulas/put_back.py); transcript.js draws it.

const PLACE_KEYS = {
  seam: "ui.putback.place.seam",
  edge: "ui.putback.place.edge",
  hole: "ui.putback.place.hole",
  fill: "ui.putback.place.fill",
};
const OUTCOMES = new Set([
  "restored",
  "still_in_edit",
  "silence",
  "cut_differently",
  "split",
  "shifted",
  "empty",
]);

/** Only words the edit lost can come back; muted and gated ones are on the timeline already. */
export const canPutBack = (hit) => hit.status === "cut" || hit.status === "unused";

/** The message key for where it goes; an unclear or missing place reads as unclear. */
export const placeKey = (kind) => PLACE_KEYS[kind] ?? "ui.putback.place.unclear";

/** The message key for what one track gets (an unknown outcome reads as restored). */
export const outcomeKey = (outcome) =>
  OUTCOMES.has(outcome) ? `ui.putback.out.${outcome}` : "ui.putback.out.restored";

/**
 * The preview as data: { text, seconds, place: { key, frame }, push: { frame, seconds, count }
 * | null, tracks: [{ track, name, key }], candidates, canConfirm }. `nameOf(trackId)` names a
 * track; the page turns the keys into words.
 */
export function describePlan(plan, { rate, nameOf }) {
  return {
    text: plan.text,
    seconds: plan.length / rate,
    place: { key: placeKey(plan.blocked ? "" : plan.site.kind), frame: plan.at },
    push:
      plan.shift > 0
        ? { frame: plan.at, seconds: plan.shift / rate, count: plan.scope.length }
        : null,
    tracks: plan.outcomes.map((o) => ({
      track: o.track,
      name: nameOf(o.track),
      key: outcomeKey(o.outcome),
    })),
    candidates: plan.site.candidates ?? [],
    canConfirm: plan.blocked === "",
  };
}

/** The put_back command's arguments: the previewed stretch and scope; `at` only for the playhead. */
export function commandArgs(media, plan, trackIds, at = null) {
  const args = { media, start: plan.start, end: plan.end, track_ids: trackIds };
  return at === null ? args : { ...args, at };
}
