// File > Open Recent as data: the start page's recent.json records -> the menu's entries.
// Pure, no DOM. Written to the signature agreed with the agent that delivers the shared model
// (recentMenuItems(records, { max, nowMs }) -> [{ path, label, detail }]); `lang` (the time's
// language) and `missing` (the folder is gone: the entry is greyed out) are additions to it.

import { relativeTime } from "./launcher-model.js";

export const MAX_RECENT_MENU = 10;

const SUFFIX = /\.kuulas$/;
const baseName = (path) => {
  const name =
    path
      .replace(/[\\/]+$/, "")
      .split(/[\\/]/)
      .pop() ?? "";
  return name.replace(SUFFIX, "") || path;
};

/**
 * `records`: [{ path, opened_utc?, exists? }] (bare path strings are accepted), newest first.
 * -> [{ path, label, detail, missing }]: the name without ".kuulas", "2 hours ago" (or ""),
 * and whether the folder is gone (`exists === false`; unknown counts as there).
 */
export function recentMenuItems(
  records,
  { max = MAX_RECENT_MENU, nowMs = Date.now(), lang = "en" } = {},
) {
  if (!Array.isArray(records)) return [];
  const seen = new Set();
  const items = [];
  for (const entry of records) {
    const record = typeof entry === "string" ? { path: entry } : entry;
    const path = record?.path;
    if (typeof path !== "string" || path === "" || seen.has(path)) continue;
    seen.add(path);
    const opened = Date.parse(record.opened_utc ?? "");
    items.push({
      path,
      label: baseName(path),
      detail: relativeTime(opened, nowMs, lang) ?? "",
      missing: record.exists === false,
    });
    if (items.length >= max) break;
  }
  return items;
}
