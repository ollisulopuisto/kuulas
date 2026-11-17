// The core-loop onboarding (the owner's sketch v2, "build it" 2026-11-12): the five keys
// of the editing loop as rows the app ticks when each command really runs, so a new user
// learns the loop by doing it. The sixth row (owner, 2026-11-17) teaches the two-step panel
// keys: open a panel with its Cmd+number key, then let a bare number act in it. The model is
// pure: tried rows, half-done steps and the hidden flag go in and come out; the counter
// lives in this browser only (core-loop prefs in app.js), like the use-hints counter
// (use-hints.js).

// The two halves of the panelkeys row: any side panel opened by its command, then any bare
// number that acts in one (1-9 jump in Markers, 1-7 play in Clipboard).
export const PANEL_COMMANDS = Object.freeze([
  "panel.show_inspector",
  "panel.show_history",
  "panel.show_markers",
  "panel.show_clipboard",
  "panel.show_material",
  "panel.show_candidates",
]);
export const NUMBER_COMMANDS = Object.freeze([
  ...Array.from({ length: 9 }, (_, i) => `marker.jump_${i + 1}`),
  ...Array.from({ length: 7 }, (_, i) => `clipboard.play_slot_${i + 1}`),
]);

export const CORE_LOOP = Object.freeze([
  { id: "in", command: "mark.in" },
  { id: "out", command: "mark.out" },
  { id: "preview", command: "transport.rehearse" },
  { id: "cut", command: "edit.remove" },
  { id: "play", command: "transport.play_before" },
  {
    id: "panelkeys",
    steps: [PANEL_COMMANDS, NUMBER_COMMANDS],
    // The keys cell shows one example of the pattern: Cmd+3, then 3.
    example: { panel: "panel.show_markers", key: "3" },
  },
]);

export const TOTAL = CORE_LOOP.length;

const KEY = "core.loop";

export const emptyCoreLoop = () => ({ tried: [], hidden: false, steps: {} });

/** The remembered panel; anything that is not the expected shape is a fresh one. */
export function readCoreLoop(prefs) {
  const stored = prefs.getJson(KEY, null);
  const known = new Set(CORE_LOOP.map((row) => row.id));
  const tried = Array.isArray(stored?.tried)
    ? [...new Set(stored.tried.filter((id) => known.has(id)))]
    : [];
  const steps = {};
  for (const row of CORE_LOOP.filter((entry) => entry.steps)) {
    if (tried.includes(row.id)) continue;
    const kept = Array.isArray(stored?.steps?.[row.id])
      ? [
          ...new Set(
            stored.steps[row.id].filter(
              (index) => Number.isInteger(index) && index >= 0 && index < row.steps.length,
            ),
          ),
        ]
      : [];
    if (kept.length > 0) steps[row.id] = kept;
  }
  return { tried, hidden: stored?.hidden === true, steps };
}

export const writeCoreLoop = (prefs, state) => prefs.setJson(KEY, state);

/**
 * `state`: { tried: [rowId], hidden, steps: { rowId: [stepIndex] } }; `command`: the command
 * that just ran. Returns { state, ticked }: `ticked` is the row that turned done now, or
 * null. A steps row turns done when every step ran at least once, in any order; until then
 * the done step indexes are remembered. The same state object comes back when the command is
 * none of the rows' business or the row was done.
 */
export function noteRun(state, command) {
  const row = CORE_LOOP.find((entry) =>
    entry.steps ? entry.steps.some((step) => step.includes(command)) : entry.command === command,
  );
  if (!row || state.tried.includes(row.id)) return { state, ticked: null };
  if (!row.steps) return { state: { ...state, tried: [...state.tried, row.id] }, ticked: row.id };
  const done = new Set(state.steps?.[row.id] ?? []);
  row.steps.forEach((step, index) => {
    if (step.includes(command)) done.add(index);
  });
  if (done.size < row.steps.length)
    return {
      state: { ...state, steps: { ...state.steps, [row.id]: [...done].sort((a, b) => a - b) } },
      ticked: null,
    };
  const steps = { ...state.steps };
  delete steps[row.id];
  return { state: { ...state, tried: [...state.tried, row.id], steps }, ticked: row.id };
}

export const triedCount = (state) => CORE_LOOP.filter((row) => state.tried.includes(row.id)).length;

export const complete = (state) => triedCount(state) === TOTAL;

/**
 * Shown on its own until the user hides it or finishes the loop; a finished loop stays
 * closed on later launches. Help > A few keys for editing opens it again either way.
 */
export const showsOnLaunch = (state) => !state.hidden && !complete(state);
