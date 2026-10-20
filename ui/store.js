// Client state: one object, re-rendered on change. Selection, focus, in/out,
// zoom and scroll are UI state: they are not edits and are not in history.
import { BUS_HEIGHT, DEFAULT_LANE, GROUP_GAP } from "./lanes.js";

const listeners = new Set();

export const initialState = () => ({
  // From the server (/api/state).
  project: null,
  head: null,
  canUndo: false,
  canRedo: false,
  words: [],
  // The names of the people the words refer to (GET /api/words), and the head the words
  // were fetched at: a command on the words waits until it equals `head`.
  people: {},
  wordsHead: null,
  // mutedInputsKey of the last server answer's project: when it changes under the same head
  // (the server merges mute clicks into one step) the words are fetched again.
  serverMutedKey: null,
  // UI state.
  selection: new Set(),
  // The transcript's word cursor and selection { cursor, anchor }, the crosstalk preview
  // of the selected words (POST /api/cut-preview) and the band it draws on the timeline.
  transcriptSelection: { cursor: -1, anchor: null },
  cutPreview: null,
  collateral: null,
  focusTrack: null,
  // A bus row is the current row (the inspector shows its Bus section); else null.
  focusBus: null,
  panel: "timeline",
  // The sidebar's tab: "inspector", "candidates" (WP18), "clipboard" (WP46) or "history" (WP8).
  sidebarTab: "inspector",
  // The History tab's pick (a step id): what Restore (Enter) applies.
  historySelected: null,
  // The step that is the current state (the head, or the step under a session marker).
  historyCurrent: null,
  // The clipboard history, newest first (GET /api/clipboard); the entry picked in the tab
  // (null: the newest) and how a paste lands: "insert" | "overwrite", "same" | "current".
  clipboard: [],
  clipboardSelected: null,
  clipboardFilter: "",
  pasteMode: "insert",
  pasteTarget: "same",
  // Cut candidates (WP18; GET /api/candidates): the rows with their timeline frames, the
  // counts, the one picked in the tab (its id), "Open only", the start of a stretch begun
  // with D, a search in progress and its result { added, dropped }, and the preview data
  // { id, from, to, skip } of the picked one (the tab's preview bar).
  candidates: [],
  candidateSummary: { open: 0, cut: 0, kept: 0 },
  candidateCurrent: null,
  candidatesOpenOnly: true,
  candidateMarkStart: null,
  candidateBusy: false,
  candidateFound: null,
  candidatePreview: null,
  // The marker picked in the Markers tab or by Next/Previous (WP19h); null for none.
  markerSelected: null,
  // The automatic "left off" marker (left-off.js): { frame, savedAt } or null. UI state only,
  // never a project marker.
  leftOff: null,
  // The narration placeholder picked on the timeline (WP43); null for none.
  placeholderSelected: null,
  playhead: 0,
  inPoint: null,
  outPoint: null,
  // The lanes a dragged range covered (WP6, ids); empty after a click.
  rangeTracks: new Set(),
  // Loop playback (WP50): on or off; the range is the marks, else the selected clips.
  loop: false,
  // Which tracks a range operation acts on (WP83, range-scope.js): "all" at every start (PLAN
  // ground rule 16: safety states reset on open; a project opens in a new window, so a new
  // store); "selected" while track headers are selected. E flips it for the session.
  rangeMode: "all",
  // The track headers clicked (Cmd+click adds): ids. Esc clears them first.
  trackSelection: new Set(),
  // Drifting and free clips (R51, GET /api/sync): looked up after an edit, never guessed on the page.
  syncClips: [],
  syncAnchors: [],
  nudgeMs: 10,
  // Quick mute length in seconds (Preferences, ui/quick-mute.js); app.js loads the remembered one.
  quickMuteS: 0.5,
  zoom: 48_000 / 20,
  scroll: 0,
  scrollY: 0,
  playing: false,
  // The engine's tape speed (signed; JKL shuttle). 1 whenever nothing is shuttling.
  speed: 1,
  // Fast listening (WP26, ui/fast-speed.js): the chosen stepless speed (1.0-2.0) and whether
  // it is switched on. Remembered per user (app.js); the pitch is kept by the engine.
  fast: { fast: 1.5, active: false },
  laneHeight: DEFAULT_LANE,
  // Lanes sized by hand (drag a header's bottom border): { trackId: px }. Remembered
  // per project with the view (view-memory.js), never in the edit history.
  laneHeights: {},
  // Buses folded to their header row (ids). View state: remembered per project with
  // the view (view-memory.js), never in the edit history. Always replaced, never mutated.
  collapsedBuses: new Set(),
  // Recompute laneHeight whenever the lane area, the tracks or the buses change.
  autoFitTracks: false,
  // Density (tokens.css --bus-h, --group-gap); app.js reads them from the tokens.
  busHeight: BUS_HEIGHT,
  groupGap: GROUP_GAP,
  density: "comfortable",
  waveformMode: "half",
  waveformScale: "auto",
  waveformGain: 1,
  // Show the Auto-Silence gate bands on the lanes (WP44); a view option.
  showGates: true,
  // The transcript words along the top of each clip when zoomed in (WP69); a per-user view option.
  showClipWords: true,
  // The clipboard preview is limited to the project's level (WP82); a per-user preference.
  clipboardLimit: true,
  // How far the latest clipboard preview was turned down: { id, db }, db 0 or less.
  clipboardLevel: null,
  followMode: "page",
  followPaused: false,
  // Where the last edit happened, for the zoom anchor; null until an edit sets it.
  lastEditPoint: null,
  fitted: false,
  live: "connecting",
  // Integrated loudness per track from the analysis (loudness-readout.js): { head, status,
  // tracks }, null until the first answer. Read-only for the headers; never an edit.
  loudness: null,
});

let state = initialState();

export const getState = () => state;

export function setState(patch) {
  state = { ...state, ...patch };
  for (const listener of listeners) listener(state, patch);
  return state;
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function resetState() {
  state = initialState();
}

/**
 * The patch a server answer makes: the server's names become the client's.
 * Given the current `state`, a selection that points at clips that no longer
 * exist (an undo removed them) is trimmed.
 */
export function serverPatch(response, state = null) {
  const patch = {};
  if ("project" in response) patch.project = response.project;
  if ("head" in response) patch.head = response.head;
  if ("can_undo" in response) patch.canUndo = response.can_undo;
  if ("can_redo" in response) patch.canRedo = response.can_redo;
  if (state && response.project) {
    const ids = new Set(
      response.project.tracks.flatMap((track) => track.clips.map((clip) => clip.id)),
    );
    const kept = [...state.selection].filter((id) => ids.has(id));
    if (kept.length !== state.selection.size) patch.selection = new Set(kept);
    const picked = state.placeholderSelected;
    if (picked && !(response.project.placeholders ?? []).some((h) => h.id === picked))
      patch.placeholderSelected = null;
  }
  return patch;
}

/**
 * What a message on the live channel does to the state: { patch, refresh,
 * notice }. `refresh` asks the caller to fetch /api/state again (another
 * window, an undo or a background job changed the project).
 */
export function reduceLive(state, message) {
  const out = { patch: {}, refresh: false };
  switch (message.type) {
    case "anchor":
      // The playhead clock (playhead-clock.js) decides whether it is current; the app
      // then applies anchorPatch.
      out.anchor = message;
      break;
    case "state_changed":
    case "hello":
      out.refresh = message.head !== undefined && message.head !== state.head;
      break;
    case "clipboard_changed":
      out.clipboard = true; // the history file changed (another window): read it again
      break;
    case "meter":
      out.meter = message.meter; // drawn by the status bar's meter (level-meter.js), not state
      break;
    case "notice":
      out.notice = { id: message.id, text: message.text };
      break;
    default:
  }
  return out;
}

/**
 * What an accepted playhead anchor does to the state. While playing the playhead in the
 * state follows the clock's extrapolation (app.js), not the anchor; stopped, the anchor's
 * frame is where the engine stopped. Playback ended (reverse reached the start, or a stop
 * from elsewhere): 1x again.
 */
export function anchorPatch(message) {
  if (message.playing) return { playing: true };
  return { playhead: message.position, playing: false, speed: 1 };
}
