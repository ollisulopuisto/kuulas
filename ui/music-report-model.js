// File > Music report… (WP25): the pure parts of the dialog. The server builds the report
// (src/kuulas/music_report.py, GET /api/music-report); this file only lays it out: the preview
// rows, the summary, the warnings, the tab-separated copy and the reason an empty report is
// empty. The DOM is music-report-dialog.js.

import { spanDots } from "./export-selection-model.js";

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

/**
 * The query string of GET /api/music-report: the format, and the selection's span in timeline
 * frames (`range` [start, end]) when only the selection is reported; none = the whole edit.
 * The HTML is asked to come as a download, which names the file after the project.
 */
export function reportQuery(format, range = null) {
  const parts = [`format=${format}`];
  if (format === "html") parts.push("download=1");
  if (range) parts.push(`start=${range[0]}`, `end=${range[1]}`);
  return parts.join("&");
}

/**
 * The line under the title when a selection exists ("" otherwise): the span it reports, or
 * (unticked) the whole edit and how to get the span back. The music report is about time, so a
 * selection that names tracks has them ignored, and the line says so.
 */
export function selectionLine(selection, only, rate, t) {
  if (!selection) return "";
  const span = spanDots(selection.range, rate);
  const line = t(only ? "ui.music_report.selection_only" : "ui.music_report.selection_off", {
    span,
  });
  return selection.trackIds ? `${line} ${t("ui.music_report.tracks_ignored")}` : line;
}

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
export function emptyReasonKey(project, onlySelection = false) {
  const music = (project?.tracks ?? []).filter((track) => track.kind === "music");
  if (music.length === 0) return "ui.music_report.empty_no_tracks";
  const live = (track) => (track.clips ?? []).some((clip) => !clip.muted);
  // Live music that is not heard in the selection's span: the selection is why it is empty.
  if (music.some((track) => !track.mute && live(track))) {
    return onlySelection ? "ui.music_report.empty_selection" : "ui.music_report.empty_silent";
  }
  if (music.some((track) => track.mute && live(track))) return "ui.music_report.empty_muted";
  return "ui.music_report.empty_no_clips";
}
