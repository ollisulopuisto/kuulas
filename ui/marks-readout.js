// The in / out / length readout in the transport corner (docs/design/transport-corner,
// C-right): what each row says, and what a typed time does. Pure (frames in, text and
// patches out), so `node --test` covers it. Marks are UI state: no undo step is involved.
import { setInPoint, setOutPoint } from "./marks.js";
import { parseTime } from "./time-parse.js";

const isFrame = (value) => typeof value === "number";

/**
 * The three rows. Each is `{ set, text }`; `text` is null when the row is not set.
 * The length is set only when both marks are and the out mark is after the in mark.
 * `format(frame, rate)` is the app's own timecode writer.
 */
export function readoutRows({ inPoint, outPoint }, rate, format) {
  const at = (frame) => (isFrame(frame) ? { set: true, text: format(frame, rate) } : null);
  const both = isFrame(inPoint) && isFrame(outPoint) && outPoint > inPoint;
  return {
    in: at(inPoint) ?? { set: false, text: null },
    out: at(outPoint) ?? { set: false, text: null },
    length: both ? at(outPoint - inPoint) : { set: false, text: null },
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
  const seconds = parseTime(text);
  if (seconds === null) return { ok: false };
  const frames = Math.round(seconds * rate);
  const pick = (marks) => ({
    ok: true,
    patch: { inPoint: marks.inPoint, outPoint: marks.outPoint },
  });
  if (which === "in") return pick(setInPoint(state, Math.min(frames, limit)));
  if (which === "out") return pick(setOutPoint(state, Math.min(frames, limit)));
  if (which === "length") {
    if (!isFrame(state.inPoint) || frames <= 0) return { ok: false };
    const out = Math.min(state.inPoint + frames, limit);
    if (out <= state.inPoint) return { ok: false };
    return pick(setOutPoint(state, out));
  }
  return { ok: false };
}
