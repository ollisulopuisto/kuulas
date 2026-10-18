// Playing a marked range (WP26/Transport): "Play selection" plays the range and stops; "Rehearse
// edit" (Hindenburg's Ctrl+Shift+Space, owner 2026-10-18) plays the join as if the range were
// already cut: from a few seconds before the in point, up to the in point, jumping to the out
// point and playing on. Nothing is edited. Pure: the engine's play-with-skip does the playing.

const hasRange = (state) =>
  (state?.inPoint ?? null) !== null &&
  (state?.outPoint ?? null) !== null &&
  state.outPoint > state.inPoint;

/** { at, until, skip } for Transport.preview, or null without a range. */
export function rehearseRequest(state, rate, preRollSeconds = 3) {
  if (!hasRange(state)) return null;
  return {
    at: Math.max(0, state.inPoint - Math.round(preRollSeconds * rate)),
    until: null,
    skip: [[state.inPoint, state.outPoint]],
  };
}

/** The marked range, played once and stopped. */
export function playSelectionRequest(state) {
  if (!hasRange(state)) return null;
  return { at: state.inPoint, until: state.outPoint, skip: null };
}
