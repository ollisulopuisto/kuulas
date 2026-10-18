// View memory (WP35): the part of the screen a user comes back to, remembered per
// project outside the project (GET/PUT /api/view-memory; never in the history).
// Pure functions turn the client state into a record and a record back into a state
// patch, with every value checked: the file is not trusted (a hand edit, an older
// version, another project of the same id). The debounced saver is the only stateful
// part, with timers injected so tests need no clock.
import { pruneLaneHeights } from "./lane-sizing.js";
import { clampLaneHeight } from "./lanes.js";
import { SAMPLE_ZOOM } from "./view.js";

export const SIDEBAR_TABS = ["inspector", "candidates", "clipboard", "markers", "history"];
const WAVEFORM_MODES = ["half", "full"];
const FOLLOW_MODES = ["page", "continuous"];
const EMPTY_EDIT_SECONDS = 30;

const num = (value) => (typeof value === "number" && Number.isFinite(value) ? value : null);
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

/** What is saved: view fields only. `whole` says the view showed the whole edit. */
export function recordOf(state, { whole = false } = {}) {
  return {
    zoom: state.zoom,
    scroll: state.scroll,
    whole,
    laneHeight: state.laneHeight,
    laneHeights: state.laneHeights ?? {},
    autoFitTracks: state.autoFitTracks === true,
    waveformMode: state.waveformMode,
    followMode: state.followMode,
    focusTrack: state.focusTrack,
    sidebarTab: state.sidebarTab,
    playhead: state.playhead,
    inPoint: state.inPoint,
    outPoint: state.outPoint,
  };
}

/**
 * The state patch a record makes for this project: { patch, whole }. Anything that is
 * not valid is left out of the patch (the default stays). `context` = { project, width,
 * totalFrames }.
 */
export function restoreFrom(record, { project, width, totalFrames }) {
  const patch = {};
  if (!record || typeof record !== "object" || Array.isArray(record)) return { patch, whole: true };
  const rate = project?.rate ?? 48000;
  const span = totalFrames > 0 ? totalFrames : EMPTY_EDIT_SECONDS * rate;
  const widest = span / Math.max(1, width);
  const zoom = num(record.zoom);
  if (zoom !== null) {
    patch.zoom = clamp(zoom, SAMPLE_ZOOM, widest);
    const scroll = num(record.scroll);
    if (scroll !== null) {
      // Same limits as clampScroll: never before the start, half a screen of room after the end.
      const visible = Math.max(1, width) * patch.zoom;
      const max = visible >= totalFrames ? 0 : totalFrames - visible / 2;
      patch.scroll = Math.round(clamp(scroll, 0, max));
    }
  }
  const lane = num(record.laneHeight);
  if (lane !== null) patch.laneHeight = clampLaneHeight(lane);
  // Lanes sized by hand: only tracks that exist here, only numbers, always within the limits.
  const own = record.laneHeights;
  if (own && typeof own === "object" && !Array.isArray(own)) {
    const numeric = Object.entries(own).filter(([, height]) => num(height) !== null);
    patch.laneHeights = pruneLaneHeights(
      Object.fromEntries(numeric.map(([id, height]) => [id, clampLaneHeight(height)])),
      project,
    );
  }
  if (typeof record.autoFitTracks === "boolean") patch.autoFitTracks = record.autoFitTracks;
  if (WAVEFORM_MODES.includes(record.waveformMode)) patch.waveformMode = record.waveformMode;
  if (FOLLOW_MODES.includes(record.followMode)) patch.followMode = record.followMode;
  if (SIDEBAR_TABS.includes(record.sidebarTab)) patch.sidebarTab = record.sidebarTab;
  if (
    typeof record.focusTrack === "string" &&
    (project?.tracks ?? []).some((track) => track.id === record.focusTrack)
  ) {
    patch.focusTrack = record.focusTrack;
  }
  const playhead = num(record.playhead);
  if (playhead !== null) patch.playhead = clamp(Math.round(playhead), 0, totalFrames);
  const inPoint = num(record.inPoint);
  const outPoint = num(record.outPoint);
  const from = inPoint === null ? null : clamp(Math.round(inPoint), 0, totalFrames);
  const to = outPoint === null ? null : clamp(Math.round(outPoint), 0, totalFrames);
  if (from !== null && to !== null && to < from) {
    patch.inPoint = null;
    patch.outPoint = null;
  } else {
    if (from !== null) patch.inPoint = from;
    if (to !== null) patch.outPoint = to;
  }
  // A view that fitted the whole edit keeps fitting it when the edit has grown since.
  return { patch, whole: record.whole === true && zoom !== null };
}

/**
 * A string that changes when the saved record should be written. While playing, the
 * play cursor moves every frame; it is left out so the save is not postponed forever
 * (the flush on page hide still writes the latest cursor).
 */
export function changeKey(state, { whole = false } = {}) {
  const record = recordOf(state, { whole });
  if (state.playing) record.playhead = null;
  return JSON.stringify(record);
}

/**
 * Debounced saving. `touch(makeRecord)` notes that something changed; the record is
 * built when the timer fires, so it is the latest. `flush()` writes at once (page hide).
 * An unchanged record is not sent; a failed save is forgotten (and tried again at the
 * next change): remembering the view is never worth an error.
 */
export function createSaver({
  save,
  delay = 800,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
}) {
  let timer = null;
  let pending = null;
  let lastSent = null;

  function send() {
    timer = null;
    if (!pending) return;
    const record = pending();
    pending = null;
    const text = JSON.stringify(record);
    if (text === lastSent) return;
    lastSent = text;
    const failed = () => {
      if (lastSent === text) lastSent = null;
    };
    try {
      const result = save(record);
      if (result && typeof result.catch === "function") result.catch(failed);
    } catch {
      failed();
    }
  }

  return {
    touch(makeRecord) {
      pending = makeRecord;
      if (timer !== null) clearTimer(timer);
      timer = setTimer(send, delay);
    },
    flush() {
      if (timer !== null) clearTimer(timer);
      send();
    },
    /** Forget what was sent, so the next record is written even if equal. */
    forget() {
      lastSent = null;
    },
  };
}
