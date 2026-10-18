// Quick actions: the palette's "Recent" group (GUI-DESIGN 3.9). The last commands the
// user ran, by id, newest first; the list lives in the user's browser storage (prefs.js).
// Moving around is not worth remembering, so a deny-list keeps seeks, zooms and panel
// hops out: the group should hold the things the user wants to do again.

export const MAX_RECENT = 8;
const KEY = "recent-commands";

const DENIED_PREFIXES = [
  "nav.",
  "track.prev",
  "track.next",
  "panel.",
  "palette.",
  "help.",
  "view.zoom_",
  "view.back",
  "view.forward",
  "transport.shuttle_",
  "marker.next",
  "marker.prev",
  "candidate.next",
  "candidate.previous",
];
const DENIED_IDS = new Set(["edit.undo", "edit.redo"]);

const denied = (id) =>
  DENIED_IDS.has(id) || DENIED_PREFIXES.some((prefix) => id.startsWith(prefix));

/** The list after `id` ran: newest first, no repeats, at most MAX_RECENT. */
export function recordRecent(list, id) {
  const kept = Array.isArray(list) ? list.filter((entry) => typeof entry === "string") : [];
  if (typeof id !== "string" || id === "" || denied(id)) return kept;
  return [id, ...kept.filter((entry) => entry !== id)].slice(0, MAX_RECENT);
}

/** The remembered ids that are still commands and can apply to this state. */
export function recentIds(list, { registry, state }) {
  if (!Array.isArray(list)) return [];
  return list.filter((id) => typeof id === "string" && registry.has(id) && registry.can(id, state));
}

/** Load the list; any damage is an empty one. */
export function loadRecent(prefs) {
  const list = prefs.getJson(KEY, []);
  return Array.isArray(list)
    ? list.filter((id) => typeof id === "string").slice(0, MAX_RECENT)
    : [];
}

export function saveRecent(prefs, list) {
  return prefs.setJson(KEY, list);
}
