// Which of the two things an edit can act on was touched last: the in/out RANGE or the
// selected CLIPS (owner, 2026-10-21: "the most recent intent wins"). Backspace, X, Alt+X,
// Cmd+X, close gap and copy act on the range after the marks were set or changed, and on
// the selected clips after clips were selected; the other one stays on screen, dimmed.
//
// Pure, and one small piece of UI state (`intent`, "range" | "clips", never saved, never in
// history). The store derives it from every patch (`intentPatch`), so a new way of selecting
// or marking needs no call here. Loop, play-selection and export keep "marks first": they
// do not read this.
import { markedRange, selectedClips } from "./selection.js";

export const INTENT_RANGE = "range";
export const INTENT_CLIPS = "clips";

const sameSet = (a, b) => {
  if (a === b) return true;
  if (!(a instanceof Set && b instanceof Set) || a.size !== b.size) return false;
  for (const item of a) if (!b.has(item)) return false;
  return true;
};

/**
 * What the next edit touches: "clips", "range" or null. With both present the latest
 * intent decides (none yet: the range, as before); with only one, that one.
 */
export function editTarget(state) {
  const range = markedRange(state) !== null;
  const clips = selectedClips(state).length > 0;
  if (range && clips) return state?.intent === INTENT_CLIPS ? INTENT_CLIPS : INTENT_RANGE;
  if (range) return INTENT_RANGE;
  return clips ? INTENT_CLIPS : null;
}

/** The marked range when it is what the next edit touches, else null. */
export function editRange(state) {
  return editTarget(state) === INTENT_RANGE ? markedRange(state) : null;
}

/** True when a range is marked but the selected clips are the target (the marks are dimmed). */
export function rangeDimmed(state) {
  return markedRange(state) !== null && editTarget(state) === INTENT_CLIPS;
}

/**
 * The `{ intent }` a patch to `state` implies, or null for no change. Marks (in, out or the
 * painted lanes) that change win a tie with a selection in the same patch: a dragged range
 * selects the clips it touched and is still a range. A selection that only shrinks because a
 * server answer dropped clips (undo, redo) is pinned by `serverPatch`, which names the intent.
 */
export function intentPatch(state, patch) {
  if ("intent" in patch) return null;
  const marksMoved =
    ("inPoint" in patch && patch.inPoint !== state.inPoint) ||
    ("outPoint" in patch && patch.outPoint !== state.outPoint);
  const next = { ...state, ...patch };
  const marked =
    (marksMoved && markedRange(next) !== null) ||
    ("rangeTracks" in patch &&
      patch.rangeTracks?.size > 0 &&
      !sameSet(patch.rangeTracks, state.rangeTracks));
  const clipped =
    "selection" in patch && patch.selection?.size > 0 && !sameSet(patch.selection, state.selection);
  const wanted = marked ? INTENT_RANGE : clipped ? INTENT_CLIPS : null;
  return wanted !== null && wanted !== state.intent ? { intent: wanted } : null;
}
