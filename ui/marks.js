// The in and out marks (I and O): pure rules, so the order can never reverse, and what
// to draw for them (a lone mark is drawn too).
import { resolveMark } from "./ghost-marker.js";

/** Set the in mark. An in mark at or after the out mark replaces the out mark. */
export function setInPoint({ outPoint }, frame) {
  const keepOut = typeof outPoint === "number" && outPoint > frame;
  return { inPoint: frame, outPoint: keepOut ? outPoint : null };
}

/** Set the out mark. An out mark at or before the in mark replaces the in mark. */
export function setOutPoint({ inPoint }, frame) {
  const keepIn = typeof inPoint === "number" && inPoint < frame;
  return { inPoint: keepIn ? inPoint : null, outPoint: frame };
}

/**
 * Place the in or out mark at `frame` (I and O), using the ghost of the last cut for the
 * partner that is not set (ghost-marker.js resolveMark): the order rule of setInPoint and
 * setOutPoint first, then the guess. `state` holds inPoint, outPoint, ghost ({ frame } or
 * null) and guessedMarks ({ in, out }: the frame a mark was guessed at, else null).
 *
 * A mark counts as guessed only while it still sits on the frame it was guessed at, so a
 * range dragged, typed or set by hand later is explicit without anyone having to reset the
 * record. Returns the patch { inPoint, outPoint, guessedMarks }.
 */
export function placeMark(state, kind, frame) {
  const base = (kind === "in" ? setInPoint : setOutPoint)(state, frame);
  const was = markDrawing(state).guessed;
  const resolved = resolveMark(
    state.ghost,
    {
      in: base.inPoint,
      out: base.outPoint,
      guessed: {
        in: was.in && base.inPoint === state.inPoint,
        out: was.out && base.outPoint === state.outPoint,
      },
    },
    kind,
    frame,
  );
  return {
    inPoint: resolved.in,
    outPoint: resolved.out,
    guessedMarks: {
      in: resolved.guessed.in ? resolved.in : null,
      out: resolved.guessed.out ? resolved.out : null,
    },
  };
}

/**
 * The frames to draw: each mark that exists, the range tint when they make one, and which
 * marks are guesses (drawn lighter and dashed, so a guess reads differently from a chosen mark).
 */
export function markDrawing({ inPoint, outPoint, guessedMarks }) {
  const inFrame = typeof inPoint === "number" ? inPoint : null;
  const outFrame = typeof outPoint === "number" ? outPoint : null;
  const range =
    inFrame !== null && outFrame !== null && outFrame > inFrame
      ? { start: inFrame, end: outFrame }
      : null;
  const guessed = {
    in: inFrame !== null && guessedMarks?.in === inFrame,
    out: outFrame !== null && guessedMarks?.out === outFrame,
  };
  return { inFrame, outFrame, range, guessed };
}

// Room kept free either side of the length label: the in and out flags are 8 px wide.
const PILL_PAD = 12;
const PILL_ROOM = 16;

/**
 * Where the length label goes on the ruler band (transport-corner mockup): a pill centred on
 * the visible part of the in/out band, `textWidth` px of text plus padding wide. Null when
 * there is no band or the visible band is narrower than the pill plus 16 px, so the label
 * never crowds the flags (the corner still shows the length). `range` is markDrawing's.
 */
export function lengthPill({ range, scroll, zoom, width, textWidth }) {
  if (!range) return null;
  const left = Math.max(0, (range.start - scroll) / zoom);
  const right = Math.min(width, (range.end - scroll) / zoom);
  const pillWidth = textWidth + PILL_PAD;
  if (right - left < pillWidth + PILL_ROOM) return null;
  const center = (left + right) / 2;
  return { x: center - pillWidth / 2, width: pillWidth, center };
}

/**
 * The patch for a plain click at `frame` while exactly one mark is set: the click is the other
 * mark, on its own side of the lone one (after I is O, before O is I). Null otherwise, so a click
 * on the wrong side, or with both or no marks, is only a click.
 */
export function implicitMarkPlan(state, frame) {
  const { inPoint, outPoint } = state;
  if (typeof inPoint === "number" && outPoint == null && frame > inPoint) {
    return { ...placeMark(state, "out", frame), rangeTracks: new Set() };
  }
  if (typeof outPoint === "number" && inPoint == null && frame < outPoint) {
    return { ...placeMark(state, "in", frame), rangeTracks: new Set() };
  }
  return null;
}
