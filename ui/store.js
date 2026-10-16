const listeners = new Set();

export const initialState = () => ({
  project: null,
  head: null,
  canUndo: false,
  canRedo: false,
  words: [],
  selection: new Set(),
  focusTrack: null,
  playhead: 0,
  inPoint: null,
  outPoint: null,
  zoom: 48_000,
  scroll: 0,
  playing: false,
  transport: null,
  laneHeight: 48,
  waveformMode: "half",
  waveformScale: "linear",
});

let state = initialState();

export function getState() {
  return state;
}

export function setState(patch) {
  state = { ...state, ...patch };
  for (const listener of listeners) listener(state);
  return state;
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function resetState() {
  state = initialState();
}
