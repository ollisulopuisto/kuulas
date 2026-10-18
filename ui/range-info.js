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
 * The status bar text. Marks read "In 0:12 · Out 0:40 · Length 0:28"; selected clips read
 * "3 clips · 4:12-9:50 · 5:38" (count, span, length). With both, the marks come first and
 * the clips after; when they say the same span, the count leads and the span is not repeated.
 * `format(frame, rate)` writes a timecode, `t(key, values)` translates. Null: nothing to say.
 */
export function rangeLine(state, rate, format, t) {
  const { inPoint, outPoint, selection, project } = state;
  const span = selectionSpan(project, selection);
  const marks = rangeInfo({ inPoint, outPoint, selection: new Set(), project });
  const markText = (info) => {
    const { inText, outText, lengthText } = formatRangeInfo(info, rate, format);
    return [
      [inText, "ui.range.in"],
      [outText, "ui.range.out"],
      [lengthText, "ui.range.length"],
    ]
      .filter(([text]) => text !== null)
      .map(([text, key]) => `${t(key)} ${text}`);
  };
  if (!span) return marks ? markText(marks).join(" · ") : null;
  let count = 0;
  for (const track of project.tracks) for (const c of track.clips) count += selection.has(c.id);
  const countText = count === 1 ? t("ui.range.clips_one") : t("ui.range.clips_many", { count });
  const same = marks?.start === span.start && marks?.end === span.end;
  if (same) return [countText, ...markText(marks)].join(" · ");
  const spanText = `${format(span.start, rate)}-${format(span.end, rate)}`;
  const clips = [countText, spanText, format(span.end - span.start, rate)];
  // A lone mark gives way to the selection, as it always did.
  const shown = marks && marks.length !== null ? markText(marks) : [];
  return [...shown, ...clips].join(" · ");
}

/** Timecodes for each side; `format(frame, rate)` is the app's own (frameToTime). */
export function formatRangeInfo(info, rate, format) {
  const at = (frame) => (frame == null ? null : format(frame, rate));
  return { inText: at(info.start), outText: at(info.end), lengthText: at(info.length) };
}
