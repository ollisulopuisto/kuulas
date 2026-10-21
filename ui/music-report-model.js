// File > Music report… (WP25): the pure parts of the dialog. The server builds the report
// (src/kuulas/music_report.py, GET /api/music-report); this file only lays it out: the preview
// rows, the summary, the warnings, the tab-separated copy and the reason an empty report is
// empty. The DOM is music-report-dialog.js.

/** The preview's columns, in order. `key` is the row field; `usage` is derived. */
export const COLUMNS = [
  { key: "order", header: "order", numeric: true },
  { key: "title", header: "title" },
  { key: "artist", header: "artist" },
  { key: "composer", header: "composer" },
  { key: "publisher", header: "publisher" },
  { key: "in_time", header: "in", numeric: true },
  { key: "duration", header: "duration", numeric: true },
  { key: "usage", header: "usage" },
];

// The copied table has every column the CSV has except the "Metadata" flag, which the
// dialog shows as warnings instead. [row field, header key].
const COPY_FIELDS = [
  ["order", "order"],
  ["title", "title"],
  ["artist", "artist"],
  ["composer", "composer"],
  ["publisher", "publisher"],
  ["isrc", "isrc"],
  ["file_name", "file_name"],
  ["in_time", "in"],
  ["out_time", "out"],
  ["duration", "duration"],
  ["usage", "usage"],
];

const usageKey = (row) => (row.background ? "music_report.background" : "music_report.featured");

/** The header text of a column (the server's own words, so the CSV and the dialog agree). */
export const headerText = (header, t) => t(`music_report.header.${header}`);

// `readable`: the preview shows the file name where a title is missing; the copy does not.
function cellOf(row, key, t, readable) {
  if (key === "usage") return t(usageKey(row));
  if (key === "title") return readable ? row.title || row.file_name : row.title;
  return String(row[key] ?? "");
}

/** One entry per report row: { cells, missing } for the table body. */
export const previewRows = (rows, t) =>
  rows.map((row) => ({
    cells: COLUMNS.map(({ key }) => cellOf(row, key, t, true)),
    missing: Boolean(row.missing_metadata),
  }));

const seconds = (stamp) => {
  const [h = 0, m = 0, s = 0] = String(stamp).split(":").map(Number);
  return h * 3600 + m * 60 + s;
};

export function stamp(total) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
}

/** { pieces, seconds, time }: how many uses and their durations added up (as reported). */
export function summaryOf(rows) {
  const total = rows.reduce((sum, row) => sum + seconds(row.duration), 0);
  return { pieces: rows.length, seconds: total, time: stamp(total) };
}

/** The pieces missing a title or an artist: [{ order, label, missing: ["title", "artist"] }]. */
export function warningsOf(rows) {
  const out = [];
  for (const row of rows) {
    if (!row.missing_metadata) continue;
    const missing = [];
    if (!row.title) missing.push("title");
    if (!row.artist) missing.push("artist");
    out.push({ order: row.order, label: row.title || row.file_name, missing });
  }
  return out;
}

// Same guard as the CSV (music_report._guard_formula): a spreadsheet runs a cell that starts
// with = + - @ as a formula.
const clean = (text) => {
  const flat = String(text).replace(/[\t\r\n]+/g, " ");
  return /^[=+\-@]/.test(flat) ? `'${flat}` : flat;
};

/** The whole report as tab-separated text, header first, ready to paste into a spreadsheet. */
export function toTsv(rows, t) {
  const head = COPY_FIELDS.map(([, header]) => headerText(header, t));
  const lines = rows.map((row) => COPY_FIELDS.map(([key]) => clean(cellOf(row, key, t, false))));
  return [head, ...lines].map((cells) => cells.join("\t")).join("\n");
}

/**
 * Why the open edit has no music in the report: the locale key. The report lists clips that are
 * not muted, on music tracks that are not muted; "silent" is what is left (automation or a gate
 * that silences them, or another track's solo).
 */
export function emptyReasonKey(project) {
  const music = (project?.tracks ?? []).filter((track) => track.kind === "music");
  if (music.length === 0) return "ui.music_report.empty_no_tracks";
  const live = (track) => (track.clips ?? []).some((clip) => !clip.muted);
  if (music.some((track) => !track.mute && live(track))) return "ui.music_report.empty_silent";
  if (music.some((track) => track.mute && live(track))) return "ui.music_report.empty_muted";
  return "ui.music_report.empty_no_clips";
}
