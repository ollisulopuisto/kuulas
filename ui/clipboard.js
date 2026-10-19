// The clipboard's pure helpers (WP46): entry names, the paste choice and where a
// paste lands. No DOM, no state of its own; edit-plans.js builds the copy and
// paste plans from these, clipboard-panel.js draws the entries.

export const PASTE_MODES = ["insert", "overwrite"];
export const PASTE_TARGETS = ["same", "current"];

/** m:ss, or h:mm:ss from an hour on. Whole seconds: a clipboard name is a hint, not a timecode. */
export function shortDuration(seconds) {
  const whole = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const s = String(whole % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/** hh:mm:ss, zero-padded: where on the timeline a copy began ("00:12:04"). */
export function timecode(seconds) {
  const whole = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  const pad = (n) => String(n).padStart(2, "0");
  const h = pad(Math.floor(whole / 3600));
  return `${h}:${pad(Math.floor((whole % 3600) / 60))}:${pad(whole % 60)}`;
}

/**
 * The automatic name of a copy: "3 clips from Olli, 00:12:04", how many clips, the first
 * track's name and where on the timeline the copy began (`at`, seconds). The length is
 * not in the name: the entry shows it beside it. `t` translates the sentence and the
 * stand-in for a track with no name.
 */
export function autoName({ trackName, clips, at = 0 }, t = (key) => key) {
  const name = trackName?.trim() ? trackName.trim() : t("ui.clipboard.untitled_track");
  return t("ui.clipboard.auto_name", { count: clips, name, at: timecode(at) });
}

/** What the panel shows for an entry: its own name, else the automatic one from its counts. */
export function entryTitle(entry, rate, t = (key) => key) {
  const own = entry.name?.trim();
  if (own) return own;
  return t("ui.clipboard.untitled", {
    count: entry.clips,
    duration: shortDuration(entry.length / rate),
  });
}

/**
 * The detail line under an entry: which project and tracks it came from, and how long it
 * is. Entries made before the track names were kept have the short form.
 */
export function entryDetails(entry, rate, t = (key) => key) {
  const duration = shortDuration(entry.length / rate);
  const tracks = (entry.tracks ?? []).map((name) => name?.trim()).filter(Boolean);
  if (tracks.length === 0 || !entry.source_name)
    return t("ui.clipboard.details_short", { duration });
  return t("ui.clipboard.details", {
    source: entry.source_name,
    tracks: tracks.join(", "),
    duration,
  });
}

/** The three views of the Clipboard tab (WP65): this project's, the shared store, other projects'. */
export const CLIPBOARD_VIEWS = ["project", "shared", "others"];

export function clipboardView(state) {
  return CLIPBOARD_VIEWS.includes(state?.clipboardView) ? state.clipboardView : "project";
}

/**
 * "5 minutes ago": `created` and `nowSeconds` are UTC epoch seconds. "" when the time is
 * not known (an entry made before the time was kept); a time ahead of this clock is "now".
 */
export function agoText(created, nowSeconds, t = (key) => key) {
  if (!Number.isFinite(created) || created <= 0) return "";
  const seconds = Math.max(0, nowSeconds - created);
  if (seconds < 60) return t("ui.clipboard.ago_now");
  if (seconds < 3600) return t("ui.clipboard.ago_minutes", { count: Math.floor(seconds / 60) });
  if (seconds < 86400) return t("ui.clipboard.ago_hours", { count: Math.floor(seconds / 3600) });
  return t("ui.clipboard.ago_days", { count: Math.floor(seconds / 86400) });
}

/**
 * The hint beside an entry whose preview was turned down to the project's level (WP82):
 * "−9 dB to match the project". `level` is `{ id, db }` from the latest preview; empty when it
 * is another entry or the change is under a dB (nothing worth saying).
 */
export function levelHint(level, entryId, t = (key) => key) {
  if (!level || level.id !== entryId || !(level.db <= -0.5)) return "";
  return t("ui.clipboard.level_hint", { db: `−${Math.abs(Math.round(level.db))}` });
}

/**
 * The metadata line of an entry: source project, track names, length and how long ago,
 * whatever of that the entry has (entries from before the metadata was kept have less).
 */
export function entryMeta(entry, rate, nowSeconds, t = (key) => key) {
  const tracks = (entry.tracks ?? []).map((name) => name?.trim()).filter(Boolean);
  return [
    entry.source_name?.trim() ?? "",
    tracks.join(", "),
    shortDuration(entry.length / rate),
    agoText(entry.created_utc, nowSeconds, t),
  ]
    .filter(Boolean)
    .join(" · ");
}

/** What the tab knows of another project's clipboard (loaded when it is opened). */
export function foreignState(state, path) {
  return state?.clipboardForeign?.[path] ?? { status: "idle", entries: [] };
}

/** A project in the Other projects list: its name and how many entries it has. */
export function projectLabel(project, t = (key) => key) {
  return `${project.name} · ${t("ui.clipboard.project_entries", { count: project.entries ?? 0 })}`;
}

/**
 * The entries a filter box leaves: every word of `query` must be found (any case) in the
 * entry's title, its track names, its source project's name or the transcript words it
 * holds (`text`). An empty query keeps all.
 */
export function filterEntries(entries, query, rate, t = (key) => key) {
  const list = entries ?? [];
  const words = String(query ?? "")
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) return list;
  return list.filter((entry) => {
    const haystack = [
      entryTitle(entry, rate, t),
      ...(entry.tracks ?? []),
      entry.source_name ?? "",
      entry.text ?? "",
    ]
      .join("\n")
      .toLowerCase();
    return words.every((word) => haystack.includes(word));
  });
}

/** How many entries "Clear old entries" keeps: the tab's number, else the default 100. */
export const DEFAULT_KEEP = 100;
export function keepCount(state) {
  const n = Number(state?.clipboardKeep);
  return Number.isInteger(n) && n >= 1 ? n : DEFAULT_KEEP;
}

/** The remembered paste choice, with defaults: insert, on the same tracks. */
export function pasteChoice(state) {
  return {
    mode: PASTE_MODES.includes(state?.pasteMode) ? state.pasteMode : "insert",
    target: PASTE_TARGETS.includes(state?.pasteTarget) ? state.pasteTarget : "same",
  };
}

/**
 * The slot -> track id mapping for "paste on the current track": slot 0 on the
 * current track, the next slots on the tracks below it, and the rest on the last
 * track when the tracks run out. null when the current track is not among them.
 */
export function pasteTargets(slots, trackIds, currentId) {
  const at = trackIds.indexOf(currentId);
  if (at < 0) return null;
  const mapping = {};
  for (let slot = 0; slot < slots; slot += 1) {
    mapping[slot] = trackIds[Math.min(trackIds.length - 1, at + slot)];
  }
  return mapping;
}

/** The clips of `trackIds` that overlap [start, end), trimmed to it. */
export function clipsInRange(project, trackIds, start, end) {
  const wanted = new Set(trackIds);
  return (project?.tracks ?? [])
    .filter((track) => wanted.has(track.id))
    .flatMap((track) =>
      track.clips
        .filter((clip) => clip.start < end && clip.start + clip.length > start)
        .map((clip) => ({
          trackId: track.id,
          trackName: track.name,
          start: Math.max(clip.start, start),
          end: Math.min(clip.start + clip.length, end),
        })),
    );
}

/** The `autoName` parts for a set of trimmed clips `[{ trackId, trackName, start, end }]`. */
export function describeClips(parts, rate) {
  if (parts.length === 0) return { trackName: "", clips: 0, seconds: 0, at: 0 };
  const first = Math.min(...parts.map((p) => p.start));
  return {
    trackName: parts[0].trackName,
    clips: parts.length,
    seconds: (Math.max(...parts.map((p) => p.end)) - first) / rate,
    at: first / rate,
  };
}
