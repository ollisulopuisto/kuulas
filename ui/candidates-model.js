// The Candidates tab and its drawing, pure (WP18 UI). Rows are what GET /api/candidates
// answers (candidates.view): timeline frames, the lanes a soft cut touches, the length of
// the recording range in seconds. candidates-panel.js draws the list, timeline.js the
// stripes; the decisions about order, stepping and geometry are here, so node tests cover them.

/** The glyph twin of a kind: a word and a shape, so colour is never the only cue. */
const KIND_ICON = { silence: "‖", filler: "…", retake: "↺", breath: "∿", marked: "◆" };

export function kindFacts(kind) {
  const known = Object.hasOwn(KIND_ICON, kind) ? kind : "marked";
  return { kind: known, icon: KIND_ICON[known], key: `ui.candidates.kind.${known}` };
}

/** By time; candidates whose audio is off the timeline (start null) last; ties by id. */
export function sortedRows(rows) {
  return [...rows].sort((a, b) => {
    if ((a.start === null) !== (b.start === null)) return a.start === null ? 1 : -1;
    return (a.start ?? 0) - (b.start ?? 0) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  });
}

/** What the list shows: all rows, or only the open ones, in time order. */
export function listedRows(rows, openOnly) {
  const sorted = sortedRows(rows);
  return openOnly ? sorted.filter((row) => row.state === "open") : sorted;
}

export const extractCurrent = (rows, id) => rows.find((row) => row.id === id) ?? null;

/**
 * The row Alt+Down or Alt+Up goes to (`direction` 1 or -1), among the rows shown; null at the ends.
 * Standing on the current one (the play cursor is at its start), it is the neighbour in
 * the list, so two candidates at one instant are both visited. Otherwise it is by
 * position: the first that starts after the cursor, the last that starts before it.
 */
export function stepTarget(rows, { currentId, playhead }, direction) {
  const placed = rows.filter((row) => row.start !== null);
  const at = placed.findIndex((row) => row.id === currentId);
  if (at >= 0 && placed[at].start === playhead) return placed[at + direction] ?? null;
  if (direction > 0) return placed.find((row) => row.start > playhead) ?? null;
  return placed.findLast((row) => row.start < playhead) ?? null;
}

/**
 * The scroll (a frame) that shows `frame`: unchanged while it is inside the view with a
 * margin of a tenth of the width on each side, else the frame comes to a quarter of the width.
 */
export function scrollToShow(frame, { scroll, zoom, width }) {
  const margin = width * zoom * 0.1;
  if (frame >= scroll + margin && frame <= scroll + width * zoom - margin) return scroll;
  return Math.max(0, Math.round(frame - width * zoom * 0.25));
}

const MIN_BAND_PX = 2;

/**
 * The open candidates as pixel bands for the timeline: [{ id, x0, x1, tracks, current,
 * flag, seconds }], the current one last so it lies on top. A candidate in several pieces
 * has a band per piece and a flag (`flag: true`) on the first only.
 */
export function candidateBands(rows, { scroll, zoom, width, currentId }) {
  const bands = [];
  for (const row of rows) {
    if (row.state !== "open") continue;
    row.spans.forEach(([from, to], index) => {
      const x0 = (from - scroll) / zoom;
      const x1 = Math.max((to - scroll) / zoom, x0 + MIN_BAND_PX);
      if (x1 < 0 || x0 > width) return;
      bands.push({
        id: row.id,
        x0,
        x1,
        tracks: row.tracks ?? [],
        current: row.id === currentId,
        flag: index === 0,
        seconds: row.seconds,
      });
    });
  }
  return bands.sort((a, b) => Number(a.current) - Number(b.current));
}

/** "cut? 2.4 s": the ruler flag's text. `format` writes the number in the UI language. */
export function flagText(row, t, format) {
  return t("ui.candidates.flag", { seconds: format(row.seconds) });
}

const FLAG_PAD_PX = 8;
/** Does the flag's text fit in its band? Narrow bands keep only the 3 px edge. */
export const flagFits = (bandPx, textPx) => bandPx >= textPx + 2 * FLAG_PAD_PX;

/**
 * The preview bar's three lengths in seconds: the play before the skipped stretch, the
 * skipped stretch itself and the play after it. null when there is nothing to skip.
 */
export function previewBar(preview, rate) {
  const skip = preview?.skip ?? [];
  if (skip.length === 0) return null;
  const skipped = skip.reduce((sum, [a, b]) => sum + (b - a), 0);
  return {
    before: (skip[0][0] - preview.from) / rate,
    skipped: skipped / rate,
    after: (preview.to - skip[skip.length - 1][1]) / rate,
  };
}
