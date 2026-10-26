// Hints from use (WP86, docs/design/TOOLBAR.md): after a number of hand mutes, tell the user once
// that Auto-Silence does it for them. Pure: the counts and the hints already shown go in and
// come out; the counter lives in this browser only (use-hints-prefs in app.js). A hint is text
// and nothing else: it never adds a button and never changes the toolbar's order.

export const HINTS = Object.freeze([
  {
    id: "auto_silence",
    commands: ["clip.mute", "clip.quick_mute"],
    after: 10,
    key: "ui.hint.use.auto_silence",
    // Running Auto-Silence once is proof the user knows it: the hint is never shown then.
    stop: ["app.auto_silence"],
  },
]);

/**
 * `state`: { counts: {hintId: n}, shown: [hintId] }; `id`: the command that just ran.
 * Returns { state, hint }: `hint` is a message key to show now, or null. The same state object
 * comes back when the command is none of the hints' business.
 */
export function noteUse(state, id) {
  let next = state;
  let hint = null;
  for (const entry of HINTS) {
    if (state.shown.includes(entry.id)) continue;
    if (entry.stop.includes(id)) {
      next = { ...next, shown: [...next.shown, entry.id] };
    } else if (entry.commands.includes(id)) {
      const count = (next.counts[entry.id] ?? 0) + 1;
      if (count >= entry.after) {
        hint = entry.key;
        next = { counts: { ...next.counts, [entry.id]: count }, shown: [...next.shown, entry.id] };
      } else {
        next = { ...next, counts: { ...next.counts, [entry.id]: count } };
      }
    }
  }
  return { state: next, hint };
}

const KEY = "use.hints";

/** The remembered counter; anything that is not the expected shape is an empty one. */
export function readUse(prefs) {
  const stored = prefs.getJson(KEY, null);
  const counts = {};
  if (stored?.counts && typeof stored.counts === "object" && !Array.isArray(stored.counts))
    for (const [id, n] of Object.entries(stored.counts))
      if (Number.isInteger(n) && n > 0) counts[id] = n;
  const shown = Array.isArray(stored?.shown)
    ? stored.shown.filter((id) => typeof id === "string")
    : [];
  return { counts, shown };
}

export const writeUse = (prefs, state) => prefs.setJson(KEY, state);
