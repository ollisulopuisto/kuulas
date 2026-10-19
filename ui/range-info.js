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

/**
 * The status bar text. The in and out marks and their length live in the transport corner
 * (marks-readout.js) and are not repeated here. Selected clips read "3 clips · 4:12-9:50 ·
 * Length 5:38" (count, span, the clips' lengths added up); when the span is exactly the marked range, only the count is
 * said. `format(frame, rate)` writes a timecode, `t(key, values)` translates. Null: nothing
 * is selected.
 */
export function rangeLine(state, rate, format, t) {
  const { inPoint, outPoint, selection, project } = state;
  const span = selectionSpan(project, selection);
  if (!span) return null;
  let count = 0;
  let total = 0; // the clips' own lengths added up, not the span (a hole between is not length)
  for (const track of project.tracks) {
    for (const c of track.clips) {
      if (!selection.has(c.id)) continue;
      count += 1;
      total += c.length;
    }
  }
  const countText = count === 1 ? t("ui.range.clips_one") : t("ui.range.clips_many", { count });
  const marks = rangeInfo({ inPoint, outPoint, selection: new Set(), project });
  const same = marks?.start === span.start && marks?.end === span.end;
  if (same) return countText;
  const spanText = `${format(span.start, rate)}-${format(span.end, rate)}`;
  return [countText, spanText, `${t("ui.range.length")} ${format(total, rate)}`].join(" · ");
}

/** Timecodes for each side; `format(frame, rate)` is the app's own (frameToTime). */
export function formatRangeInfo(info, rate, format) {
  const at = (frame) => (frame == null ? null : format(frame, rate));
  return { inText: at(info.start), outText: at(info.end), lengthText: at(info.length) };
}
