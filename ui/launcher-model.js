// The start screen's recent-projects list: pure functions from a stored record to what a row
// shows. No DOM. The start page (src/kuulas/desktop.py launcher_html) inlines this file, so it
// has no imports.

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

const startOfDay = (ms) => {
  const d = new Date(ms);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
};

/** "2 min ago", "yesterday", "3 days ago" in `lang`; null when `thenMs` is not a time. */
export function relativeTime(thenMs, nowMs, lang) {
  if (typeof thenMs !== "number" || !Number.isFinite(thenMs)) return null;
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
  const diff = Math.max(0, nowMs - thenMs);
  if (diff < MIN) return rtf.format(0, "second");
  if (diff < HOUR) return rtf.format(-Math.floor(diff / MIN), "minute");
  const sameDay = startOfDay(thenMs) === startOfDay(nowMs);
  if (diff < 6 * HOUR || (sameDay && diff < DAY)) {
    return rtf.format(-Math.floor(diff / HOUR), "hour");
  }
  const days = Math.max(1, Math.round((startOfDay(nowMs) - startOfDay(thenMs)) / DAY));
  if (days < 7) return rtf.format(-days, "day");
  if (days < 30) return rtf.format(-Math.floor(days / 7), "week");
  if (days < 365) return rtf.format(-Math.floor(days / 30), "month");
  return rtf.format(-Math.floor(days / 365), "year");
}

const UNITS = ["B", "kB", "MB", "GB", "TB"];

/** "1.5 kB", "250 MB" (binary steps, one decimal under 10); null when not a size. */
export function formatSize(bytes, lang) {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) return null;
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit > 0 && value < 10 ? 1 : 0;
  const number = new Intl.NumberFormat(lang, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
  return `${number} ${UNITS[unit]}`;
}

/** "m:ss" or "h:mm:ss"; null when not a duration. */
export function formatDuration(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return null;
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/** The project's name: the folder name without the `.kuulas` suffix. */
export function folderName(path) {
  const last = path.replaceAll("\\", "/").replace(/\/+$/, "").split("/").pop() ?? "";
  return last.endsWith(".kuulas") ? last.slice(0, -".kuulas".length) : last;
}

/**
 * What one row shows. `record` is the stored one ({path, exists, opened_utc, tracks,
 * duration_s, size_bytes}; every field but path may be absent), `labels` the translated chip
 * names. A chip exists only for a fact that is known.
 */
export function rowModel(record, nowMs, lang, labels) {
  const chips = [];
  const add = (key, text, title) => {
    if (text === null || text === undefined) return;
    chips.push({ key, label: labels[key], text, ...(title ? { title } : {}) });
  };
  const opened = record.opened_utc
    ? relativeTime(Date.parse(record.opened_utc), nowMs, lang)
    : null;
  add("opened", opened);
  add("tracks", Number.isInteger(record.tracks) ? String(record.tracks) : null);
  add("duration", formatDuration(record.duration_s));
  add("size", formatSize(record.size_bytes, lang), labels.size_tip);
  const missing = record.exists === false;
  return {
    path: record.path,
    name: folderName(record.path),
    missing,
    note: missing ? labels.missing : null,
    chips,
  };
}

/** The row to focus after `key` from row `current` (-1: none yet); null for other keys. */
export function nextRow(current, key, count) {
  if (count < 1) return null;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  if (key === "ArrowDown") return current < 0 ? 0 : Math.min(current + 1, count - 1);
  if (key === "ArrowUp") return current < 0 ? count - 1 : Math.max(current - 1, 0);
  return null;
}

/** The most recent projects that get a Cmd/Ctrl+digit key (one digit each). */
export const MAX_KEYED = 9;

/**
 * The key chip of each row: "⌘1" on a Mac, "Ctrl+1" elsewhere (the text keymap-config.js
 * formatCombo gives "Mod+1"; this file is inlined into the start page, which cannot import).
 * Rows past the ninth get null. `platform`: "mac" or "other".
 */
export function rowKeyChips(count, platform) {
  const mod = platform === "mac" ? "⌘" : "Ctrl+";
  return Array.from({ length: Math.max(0, count) }, (_, i) =>
    i < MAX_KEYED ? `${mod}${i + 1}` : null,
  );
}

/**
 * The row index (0-based) a key press opens, or null. Cmd+digit on a Mac, Ctrl+digit
 * elsewhere, no other modifier; the digit is read by position (`code`), the same on a Finnish
 * board. A digit past the last row opens nothing.
 */
export function rowForKey(event, platform, count) {
  const wanted =
    platform === "mac" ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
  if (!wanted || event.altKey || event.shiftKey || event.repeat) return null;
  const match = /^(?:Digit|Numpad)([1-9])$/.exec(event.code ?? "");
  if (match === null) return null;
  const index = Number(match[1]) - 1;
  return index < count ? index : null;
}
