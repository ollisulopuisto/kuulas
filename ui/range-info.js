// What the status bar says about the marked or selected section: where it starts, where
// it ends and how long it is. Pure (frames in, text out), so `node --test` covers it.
import { selectionSpan } from "./view.js";

/**
 * The section to report, in frames, or null when there is nothing to show.
 * Complete in/out marks (out after in) win over a selection, as for Shift+Z; a lone
 * mark is reported by itself unless a selection can say more.
 */
export function rangeInfo({ inPoint, outPoint, selection, project }) {
  const hasIn = inPoint != null;
  const hasOut = outPoint != null;
  if (hasIn && hasOut && outPoint > inPoint) {
    return { source: "marks", start: inPoint, end: outPoint, length: outPoint - inPoint };
  }
  const span = selectionSpan(project, selection);
  if (span) {
    return { source: "selection", start: span.start, end: span.end, length: span.end - span.start };
  }
  if (!hasIn && !hasOut) return null;
  // A lone mark, or marks in the wrong order: show them, but no length.
  return { source: "marks", start: inPoint ?? null, end: outPoint ?? null, length: null };
}

/** Timecodes for each side; `format(frame, rate)` is the app's own (frameToTime). */
export function formatRangeInfo(info, rate, format) {
  const at = (frame) => (frame == null ? null : format(frame, rate));
  return { inText: at(info.start), outText: at(info.end), lengthText: at(info.length) };
}
