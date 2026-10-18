// "Where I left off": an automatic marker that is NOT a project marker. It is the position
// the project was saved at (resume.json / the view memory, see view-memory.js), shown as a
// distinct flag on the ruler and as a pinned first row in the Markers tab, and the target of
// "Go to where I left off". It lives only in the UI state (`leftOff`), never in
// `project.markers`, so it makes no history step and no change in the project file. Pure
// functions only; no DOM, so node --test covers them.

export const LEFT_OFF_ID = "left-off";
/** How far past the ruler's edge a flag is still drawn (its notch is this wide). */
const EDGE_PX = 10;

/**
 * The left-off position a restored view record stands for: { frame, savedAt } or null.
 * Clamped to the edit's length (the edit may be shorter than when it was saved). Nothing at
 * the start: "left off at 0" is not worth a flag.
 */
export function leftOffOf(view, totalFrames) {
  const playhead = view?.playhead;
  if (typeof playhead !== "number" || !Number.isFinite(playhead)) return null;
  const frame = Math.max(0, Math.min(Math.round(playhead), Math.max(0, totalFrames)));
  if (frame <= 0) return null;
  return { frame, savedAt: typeof view.saved_at === "string" ? view.saved_at : null };
}

/** The position as it is right now (Mod+S): { frame, savedAt } or null at the start. */
export function leftOffHere(playhead, now) {
  const frame = Math.round(playhead);
  if (!Number.isFinite(frame) || frame <= 0) return null;
  return { frame, savedAt: now.toISOString().replace(/\.\d+Z$/, "Z") };
}

const pad = (n) => String(n).padStart(2, "0");

/**
 * "Sun 18 Oct, 21.58" (fi: "su 18.10., 21.58") for a stored UTC time. The zone is the
 * viewer's own unless `timeZone` says otherwise (tests); for the owner that is Helsinki.
 * "" for a missing or unreadable time.
 */
export function describeMoment(savedAt, { language = "en", timeZone } = {}) {
  const date = savedAt ? new Date(savedAt) : null;
  if (!date || Number.isNaN(date.getTime())) return "";
  const locale = language === "fi" ? "fi-FI" : "en-GB";
  const zone = timeZone ? { timeZone } : {};
  const day = new Intl.DateTimeFormat(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    ...zone,
  }).format(date);
  const parts = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    ...zone,
  }).formatToParts(date);
  const part = (type) => Number(parts.find((p) => p.type === type).value);
  return `${day}, ${pad(part("hour"))}.${pad(part("minute"))}`;
}

/**
 * The words for the notice ("notice") or the Markers row ("row"): "Back where you left off:
 * 12:34 (Sun 18 Oct, 21.58)". `t(key, params)` translates, `clock(seconds)` formats a
 * position; both are the UI's own, passed in so this stays pure. Without a saved time the
 * short form leaves the parenthesis out.
 */
export function leftOffText(leftOff, rate, { t, clock, language, timeZone }, kind) {
  const position = clock(leftOff.frame / rate);
  const moment = describeMoment(leftOff.savedAt, { language, timeZone });
  return moment
    ? t(`ui.resume.${kind}`, { position, moment })
    : t(`ui.resume.${kind}_short`, { position });
}

/** The pinned row of the Markers tab: { id, frame, seconds, savedAt } or null. */
export function leftOffRow(leftOff, rate) {
  if (!leftOff) return null;
  return {
    id: LEFT_OFF_ID,
    frame: leftOff.frame,
    seconds: leftOff.frame / rate,
    savedAt: leftOff.savedAt,
  };
}

/** The ruler flag: { x } for the visible range, or null (none, or off screen). */
export function leftOffFlag(leftOff, { scroll, zoom, width }) {
  if (!leftOff) return null;
  const x = (leftOff.frame - scroll) / zoom;
  if (x < -EDGE_PX || x > width + EDGE_PX) return null;
  return { x };
}
