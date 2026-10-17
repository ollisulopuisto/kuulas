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
  // UI state.
  selection: new Set(),
  focusTrack: null,
  // A bus row is the current row (the inspector shows its Bus section); else null.
  focusBus: null,
  panel: "timeline",
  playhead: 0,
  inPoint: null,
  outPoint: null,
  zoom: 48_000 / 20,
  scroll: 0,
  scrollY: 0,
  playing: false,
  laneHeight: DEFAULT_LANE,
  // Density (tokens.css --bus-h, --group-gap); app.js reads them from the tokens.
  busHeight: BUS_HEIGHT,
  groupGap: GROUP_GAP,
  density: "comfortable",
  waveformMode: "half",
  waveformScale: "linear",
  waveformGain: 1,
  followMode: "page",
  followPaused: false,
  // Where the last edit happened, for the zoom anchor; null until an edit sets it.
  lastEditPoint: null,
  fitted: false,
  live: "connecting",
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
    case "position":
      out.patch = { playhead: message.position, playing: message.playing };
      break;
    case "state_changed":
    case "hello":
      out.refresh = message.head !== undefined && message.head !== state.head;
      break;
    case "notice":
      out.notice = { id: message.id, text: message.text };
      break;
    default:
  }
  return out;
}
