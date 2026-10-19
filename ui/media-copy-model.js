// File > Locate media… and File > Send a copy… (WP39, WP32): the pure parts of the two
// dialogs. The server does the work (src/kuulas/send_copy.py, Session.locate_media); the DOM
// is in locate-dialog.js and send-copy-dialog.js.

/** What audio goes in a copy: nothing, the parts the edit plays (2 s either side), everything. */
export const MEDIA_CHOICES = Object.freeze(["none", "used", "all"]);
export const DEFAULT_MEDIA_CHOICE = "used";

/** The notice offered when a project opens with missing audio, or null when none is missing. */
export function missingNotice(missing) {
  const count = missing?.length ?? 0;
  return count > 0 ? { key: "ui.locate.notice", values: { count } } : null;
}

/** The folder typed or chosen, or null when there is none. */
export function folderOf(text) {
  const folder = String(text ?? "").trim();
  return folder === "" ? null : folder;
}

/** One line for a locate report: how many of the files looked for were found. */
export function locateSummary(report) {
  const found = report.found.length;
  const left = report.still_missing.length;
  return { key: "ui.locate.summary", values: { found, total: found + left, left } };
}

/** "250 MB", "1.5 GB". A file under a megabyte counts as one, nothing as 0. */
export function sizeText(bytes) {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  return `${bytes > 0 ? Math.max(1, Math.round(bytes / 1e6)) : 0} MB`;
}

/** The three choices with the size the server estimated for each (null before it answered). */
export function choiceRows(plan) {
  return MEDIA_CHOICES.map((id) => ({
    id,
    size: plan?.[id] ? sizeText(plan[id].bytes) : null,
  }));
}

/** The body for POST /api/send-copy, or { ok: false, key } when the folder is missing. */
export function sendCopyRequest({ folder, media }) {
  const where = folderOf(folder);
  if (where === null) return { ok: false, key: "ui.send_copy.pick_folder" };
  return {
    ok: true,
    body: { folder: where, media: MEDIA_CHOICES.includes(media) ? media : DEFAULT_MEDIA_CHOICE },
  };
}
