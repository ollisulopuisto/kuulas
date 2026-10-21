// Series (docs/design/SERIES.md): settings shared by the episodes of a show. The server holds
// the series and decides what differs (src/kuulas/series_actions.py); this file only words it
// and checks what the dialogs send. Pure, no DOM.

import { folderName, isAbsolutePath } from "./project-name.js";

/** The sections a series carries, in the order the server lists them. */
export const SECTIONS = ["layout", "auto_silence", "automix"];

/**
 * The status-bar chip: null when the project is in no series, else { text, title, differs }.
 * `state.series` is the last status from the server ({ found, differs }); before it arrives
 * the chip names the series without a verdict.
 */
export function seriesChip(state, t) {
  const link = state?.project?.series;
  if (!link?.id) return null;
  const status = state?.series ?? null;
  const differs = Array.isArray(status?.differs) && status.differs.length > 0;
  const name = link.name ?? "";
  const text = differs ? t("ui.series.chip_differs", { name }) : t("ui.series.chip", { name });
  let title = t("ui.series.same");
  if (status && status.found === false) title = t("ui.series.missing");
  else if (differs) title = t("ui.series.differs", { sections: sectionsText(status.differs, t) });
  return { text, title, differs };
}

/** "the tracks, Auto-Silence": the differing sections in words. */
export function sectionsText(sections, t) {
  return SECTIONS.filter((section) => sections.includes(section))
    .map((section) => t(`ui.series.section.${section}`))
    .join(", ");
}

/** The next episode's name: the last number in the name plus one, padding kept. */
export function nextEpisodeName(name) {
  const text = typeof name === "string" ? name.trim() : "";
  if (text === "") return "";
  const matches = [...text.matchAll(/\d+/g)];
  if (matches.length === 0) return `${text} 2`;
  const last = matches[matches.length - 1];
  const next = String(Number(last[0]) + 1).padStart(last[0].length, "0");
  return text.slice(0, last.index) + next + text.slice(last.index + last[0].length);
}

/** Where a new episode goes by default: beside the open project, named as the next one. */
export function episodeDefaults(projectPath) {
  const path = typeof projectPath === "string" ? projectPath.replace(/[\\/]+$/, "") : "";
  if (path === "") return { parent: "", name: "" };
  const cut = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  const parent = cut > 0 ? path.slice(0, cut) : "";
  const stem = path.slice(cut + 1).replace(/\.kuulas$/i, "");
  return { parent, name: nextEpisodeName(stem) };
}

/** The body for POST /api/series/new-episode, or { ok: false, field, key }. */
export function newEpisodeRequest({ parent, name, seriesId }) {
  if (!seriesId) return { ok: false, field: "series", key: "ui.series.need_series" };
  const folder = folderName(name);
  if (!folder.ok) return { ok: false, field: "name", key: folder.key };
  const where = String(parent ?? "").trim();
  if (!isAbsolutePath(where)) return { ok: false, field: "parent", key: "ui.project.need_folder" };
  return { ok: true, body: { parent: where, name: String(name).trim(), series_id: seriesId } };
}

/**
 * The body for POST /api/series/save: a linked project saves into its series; otherwise an
 * existing series chosen in the dialog (`seriesId`), else a new one that needs a name.
 * `autoSilence`: the Auto-Silence options the page has now (null: the server's copy).
 */
export function seriesSaveRequest({ linked, name, seriesId, autoSilence }) {
  const body = {};
  const typed = typeof name === "string" ? name.trim() : "";
  if (!linked) {
    if (seriesId) body.series_id = seriesId;
    else if (typed === "") return { ok: false, field: "name", key: "ui.series.need_name" };
    else body.name = typed;
  } else if (typed !== "") body.name = typed;
  if (autoSilence && typeof autoSilence === "object") body.auto_silence = autoSilence;
  return { ok: true, body };
}
