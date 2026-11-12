// The core-loop onboarding (the owner's sketch v2, "build it" 2026-11-12): the five keys
// of the editing loop as rows the app ticks when each command really runs, so a new user
// learns the loop by doing it. The model is pure: tried rows and the hidden flag go in
// and come out; the counter lives in this browser only (core-loop prefs in app.js), like
// the use-hints counter (use-hints.js).

export const CORE_LOOP = Object.freeze([
  { id: "in", command: "mark.in" },
  { id: "out", command: "mark.out" },
  { id: "preview", command: "transport.rehearse" },
  { id: "cut", command: "edit.remove" },
  { id: "play", command: "transport.play_before" },
]);

export const TOTAL = CORE_LOOP.length;

const KEY = "core.loop";

export const emptyCoreLoop = () => ({ tried: [], hidden: false });

/** The remembered panel; anything that is not the expected shape is a fresh one. */
export function readCoreLoop(prefs) {
  const stored = prefs.getJson(KEY, null);
  const known = new Set(CORE_LOOP.map((row) => row.id));
  const tried = Array.isArray(stored?.tried)
    ? [...new Set(stored.tried.filter((id) => known.has(id)))]
    : [];
  return { tried, hidden: stored?.hidden === true };
}

export const writeCoreLoop = (prefs, state) => prefs.setJson(KEY, state);

/**
 * `state`: { tried: [rowId], hidden }; `command`: the command that just ran. Returns
 * { state, ticked }: `ticked` is the row that turned done now, or null. The same state
 * object comes back when the command is none of the rows' business or the row was done.
 */
export function noteRun(state, command) {
  const row = CORE_LOOP.find((entry) => entry.command === command);
  if (!row || state.tried.includes(row.id)) return { state, ticked: null };
  return { state: { ...state, tried: [...state.tried, row.id] }, ticked: row.id };
}

export const triedCount = (state) => CORE_LOOP.filter((row) => state.tried.includes(row.id)).length;

export const complete = (state) => triedCount(state) === TOTAL;

/**
 * Shown on its own until the user hides it or finishes the loop; a finished loop stays
 * closed on later launches. Help > A few keys for editing opens it again either way.
 */
export const showsOnLaunch = (state) => !state.hidden && !complete(state);
