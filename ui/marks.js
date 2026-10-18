// The in and out marks (I and O): pure rules, so the order can never reverse, and what
// to draw for them (a lone mark is drawn too).

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

/** The frames to draw: each mark that exists, and the range tint when they make one. */
export function markDrawing({ inPoint, outPoint }) {
  const inFrame = typeof inPoint === "number" ? inPoint : null;
  const outFrame = typeof outPoint === "number" ? outPoint : null;
  const range =
    inFrame !== null && outFrame !== null && outFrame > inFrame
      ? { start: inFrame, end: outFrame }
      : null;
  return { inFrame, outFrame, range };
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
