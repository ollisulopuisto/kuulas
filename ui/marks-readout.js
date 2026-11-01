// The in / out / length readout in the transport corner (docs/design/transport-corner,
// C-right): what each row says, and what a typed time does. Pure (frames in, text and
// patches out), so `node --test` covers it. Marks are UI state: no undo step is involved.
import { setInPoint, setOutPoint } from "./marks.js";
import { resolveTime } from "./time-jump.js";

const isFrame = (value) => typeof value === "number";

/**
 * The three rows. Each is `{ set, text }`; `text` is null when the row is not set.
 * The length is set only when both marks are and the out mark is after the in mark.
 * `format(frame, rate)` is the app's own timecode writer.
 *
 * `liveEnd` (frames, optional) is the take's place while recording: with an in mark and
 * no out mark the length row runs from the in mark to it, flagged `live: true` so the
 * corner can say it keeps counting. A set out mark always wins over the live end.
 */
export function readoutRows({ inPoint, outPoint }, rate, format, liveEnd = null) {
  const at = (frame) => (isFrame(frame) ? { set: true, text: format(frame, rate) } : null);
  const both = isFrame(inPoint) && isFrame(outPoint) && outPoint > inPoint;
  const live = !both && isFrame(inPoint) && isFrame(liveEnd) && liveEnd > inPoint;
  return {
    in: at(inPoint) ?? { set: false, text: null },
    out: at(outPoint) ?? { set: false, text: null },
    length: both
      ? at(outPoint - inPoint)
      : live
        ? { ...at(liveEnd - inPoint), live: true }
        : { set: false, text: null },
  };
}

/**
 * A time typed into one row ("in", "out" or "length"): `{ ok: true, patch }` with the new
 * `inPoint` and `outPoint` (frames), or `{ ok: false }` when the text is not a time or
 * cannot apply. Marks keep the order rules of the I and O keys (marks.js). Typing the
 * length moves the out mark to in + length. `limit` (frames, optional) is the end of the
 * edit: later times are clamped to it.
 */
export function entryPatch(which, text, state, rate, limit = Number.POSITIVE_INFINITY) {
  // A leading + or - moves the mark from where it is (an unset mark: from the play cursor).
  const end = Number.isFinite(limit) ? limit : Number.MAX_SAFE_INTEGER;
  const pick = (marks) => ({
    ok: true,
    patch: { inPoint: marks.inPoint, outPoint: marks.outPoint },
  });
  const from = (frame) => (isFrame(frame) ? frame : (state.playhead ?? 0));
  if (which === "in" || which === "out") {
    const frames = resolveTime(text, { from: from(state[`${which}Point`]), end, rate });
    if (frames === null) return { ok: false };
    return pick((which === "in" ? setInPoint : setOutPoint)(state, frames));
  }
  if (which === "length") {
    if (!isFrame(state.inPoint)) return { ok: false };
    const now = isFrame(state.outPoint) ? state.outPoint - state.inPoint : 0;
    const frames = resolveTime(text, { from: now, end, rate });
    if (frames === null || frames <= 0) return { ok: false };
    const out = Math.min(state.inPoint + frames, limit);
    if (out <= state.inPoint) return { ok: false };
    return pick(setOutPoint(state, out));
  }
  return { ok: false };
}
