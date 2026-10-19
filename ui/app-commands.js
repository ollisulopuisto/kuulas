// The commands the editor can do today, registered by id (ids from keymap-default.js).
// Everything else in the keymap is "planned" until its work package lands.

import { busOfFocus, collapseAllChange, collapseChange } from "./bus-collapse.js";
import { canRestore } from "./history-model.js";
import { rangeAvailable } from "./loop-range.js";
import { setInPoint, setOutPoint } from "./marks.js";
import { playSelectionRequest, rehearseRequest } from "./rehearse.js";
import { PAUSE_CHOICES } from "./transcript-model.js";

/** The next or previous track's id; stops at the ends; null without a project. */
export function stepTrack(project, current, direction) {
  const tracks = project?.tracks ?? [];
  if (tracks.length === 0) return null;
  const at = tracks.findIndex((track) => track.id === current);
  if (at < 0) return direction > 0 ? tracks[0].id : tracks[tracks.length - 1].id;
  return tracks[Math.min(tracks.length - 1, Math.max(0, at + direction))].id;
}

/** Screen pixels one plain Left/Right press moves the play cursor (Hindenburg-style fine nudge). */
export const NUDGE_PIXELS = 4;

/**
 * Playhead steps in frames: `nudge` is 4 screen pixels at the current zoom (`zoom` is frames
 * per pixel; at least 1 frame), `near` 1 s (Shift) and `fine` 10 ms (Alt).
 */
export function seekOffsets(rate, zoom = 1) {
  const perPixel = Number.isFinite(zoom) && zoom > 0 ? zoom : 1;
  return {
    nudge: Math.max(1, Math.round(perPixel * NUDGE_PIXELS)),
    near: rate,
    fine: Math.round(rate / 100),
  };
}

/** P (Hindenburg): how many seconds before the playhead it starts playing. */
export const PREROLL_SECONDS = 3;

/** The frame P starts from: `seconds` before the playhead, never before the start. */
export function prerollStart(playhead, rate, seconds = PREROLL_SECONDS) {
  return Math.max(0, Math.round(playhead - rate * seconds));
}

const hasProject = (state) => Boolean(state?.project);
// Every command has a one-line description, cmd.<id>.hint in the catalogs (help.test.js
// fails for a ready command without one).
const hint = (id) => ({ hintKey: `cmd.${id}.hint` });

/**
 * `actions` is app.js's action table; `app` the few things the keymap needs from it:
 * undo, redo, chooseMedia, focusName, seek(frame), totalFrames(), patch(statePatch),
 * getState(), openPalette(), openKeys(), openHelp(), importKeys(), exportKeys(), resetKeys().
 */
export function registerAppCommands(registry, { actions, app }) {
  const def = (id, run, can = null) => registry.register(id, run, { can, ...hint(id) });
  const rate = () => app.getState().project?.rate ?? 48000;
  const moveBy = (frames) => () => {
    const { playhead = 0 } = app.getState();
    app.seek(Math.min(app.totalFrames(), Math.max(0, playhead + frames)));
  };
  const offsets = () => seekOffsets(rate(), app.getState().zoom);

  def("transport.play", () => actions.togglePlay());
  // What a drag does: paint a range, or move the clip (a preference, drag-mode.js).
  def("view.drag_mode", () => actions.toggleDragMode());
  // What a two-finger trackpad scroll does: zoom, or scroll (a preference, wheel.js).
  def("view.wheel_mode", () => actions.toggleWheelMode());
  // The transcript words along the top of each clip when zoomed in (WP69, clip-words.js).
  def("view.clip_words", () => actions.toggleClipWords());
  // Whether the clipboard preview is turned down to the project's level (WP82).
  def("view.clipboard_limit", () => actions.toggleClipboardLimit());
  def(
    "transport.play_before",
    () => actions.playFrom(prerollStart(app.getState().playhead ?? 0, rate())),
    hasProject,
  );
  // The marked range: played once (Shift+Space), or rehearsed as if cut (Mod+Shift+Space).
  def(
    "transport.play_selection",
    () => actions.playRequest(playSelectionRequest(app.getState())),
    (state) => hasProject(state) && playSelectionRequest(state) !== null,
  );
  def(
    "transport.rehearse",
    () => actions.playRequest(rehearseRequest(app.getState(), rate())),
    (state) => hasProject(state) && rehearseRequest(state, 48000) !== null,
  );
  // On needs a range to loop; off is always possible.
  def(
    "transport.loop",
    () => actions.toggleLoop(),
    (state) => Boolean(state?.project) && (state.loop === true || rangeAvailable(state) !== null),
  );
  def("transport.shuttle_forward", () => actions.shuttle("l"), hasProject);
  def("transport.shuttle_back", () => actions.shuttle("j"), hasProject);
  def("transport.shuttle_stop", () => actions.shuttle("k"), hasProject);
  def("transport.speed", () => actions.fastListening(), hasProject);
  def("transport.speed_down", () => actions.fastNudge(-1), hasProject);
  def("transport.speed_up", () => actions.fastNudge(1), hasProject);
  def("transport.speed_reset", () => actions.fastReset(), hasProject);
  def("nav.home", () => actions.goHome());
  def("panel.next", () => actions.cyclePanel(1));
  def("panel.previous", () => actions.cyclePanel(-1));
  def("view.toggle", () => actions.toggleView(), hasProject);
  def("view.fit", () => actions.fitView(), hasProject);
  def("view.fit_selection", () => actions.fitSelection(), hasProject);
  def("view.fit_tracks", () => actions.fitTracks(), hasProject);
  def("view.auto_fit_tracks", () => actions.toggleAutoFitTracks(), hasProject);
  def("view.back", () => actions.viewBack(), hasProject);
  // Collapsed buses (view state, no history step). The commands act on the bus in focus
  // (the focused bus, or the bus of the focused track) and fold the focus onto the bus
  // header, since the track it was on is hidden afterwards.
  const collapseBus = (collapse) => () => {
    const state = app.getState();
    const next = collapseChange(state, collapse);
    if (!next) return;
    const patch = { collapsedBuses: next };
    if (collapse) Object.assign(patch, { focusBus: busOfFocus(state), focusTrack: null });
    app.patch(patch);
  };
  def("bus.collapse", collapseBus(true), (state) => collapseChange(state, true) !== null);
  def("bus.expand", collapseBus(false), (state) => collapseChange(state, false) !== null);
  const collapseAll = (collapse) => () => {
    const next = collapseAllChange(app.getState(), collapse);
    if (next) app.patch({ collapsedBuses: next });
  };
  def(
    "view.collapse_all_buses",
    collapseAll(true),
    (state) => collapseAllChange(state, true) !== null,
  );
  def(
    "view.expand_all_buses",
    collapseAll(false),
    (state) => collapseAllChange(state, false) !== null,
  );
  def("view.reset_remembered", () => actions.resetRememberedView(), hasProject);
  // View > Break paragraphs at pauses over: one command per choice (no project needed;
  // it is a user preference, remembered with the other view settings).
  for (const choice of PAUSE_CHOICES) {
    def(`view.pause_${choice.id}`, () => actions.setPauseBreak(choice.id));
  }
  // View > Language: a user preference (no project needed), kept on the server.
  for (const choice of ["auto", "fi", "en"]) {
    def(`view.language_${choice}`, () => actions.setLanguageChoice(choice));
  }
  def("view.forward", () => actions.viewForward(), hasProject);
  def("view.zoom_in", () => actions.zoomStep(1), hasProject);
  def("view.zoom_out", () => actions.zoomStep(-1), hasProject);
  def(
    "edit.undo",
    () => app.undo(),
    (state) => Boolean(state?.canUndo),
  );
  def(
    "edit.redo",
    () => app.redo(),
    (state) => Boolean(state?.canRedo),
  );
  def(
    "history.restore",
    () => app.restoreStep(),
    (state) => canRestore(state),
  );
  def("history.open", () => app.openHistory());
  def("app.import", () => app.chooseMedia());
  // File > New project… / Open project… (WP74): a window of its own; no project needed.
  def("app.new", () => app.newProject());
  def("app.open", () => app.openProject());
  // File > Statistics… (WP70): runtime, counts, talk, work and sizes of this session.
  def("app.statistics", () => app.openStatistics(), hasProject);
  // File > Locate media… (WP39) and Send a copy… (WP32): no default key (the Finnish layout
  // leaves no free one that is not AltGr or Shift+digit); both are in the File menu.
  def("app.locate_media", () => app.openLocateMedia(), hasProject);
  def("app.send_copy", () => app.openSendCopy(), hasProject);
  // Transport > Record… (WP12a) and how a take is stopped (a preference: two steps by default).
  def("transport.record", () => app.openRecord(), hasProject);
  def("record.stop_mode", () => app.cycleStopMode());
  // Pre-roll before Record (WP12c): off / 10 / 30 / 60 (default) / 120 s.
  def("record.preroll", () => app.cyclePreroll());
  def("gate.open_stretch", () => app.openGateStretch(), hasProject);
  // Track > Auto: these three had a menu item and a key but no handler (greyed out).
  def("app.auto_silence", () => app.autoSilence(), hasProject);
  def("app.automix", () => app.duckMicrophones(), hasProject);
  def("app.transcribe", () => app.transcribeTrack("local"), hasProject);
  // Transcribe on Colab (WP78): after a notice that the audio is uploaded to Google.
  def("app.transcribe_colab", () => app.transcribeTrack("colab"), hasProject);
  def("app.transcribe_restart", () => app.restartTranscriptions(), hasProject);
  def("app.colab_settings", () => app.openColabSettings());
  def("app.colab_signin", () => app.openColabSignin());
  def(
    "rename",
    () => app.focusName(),
    (state) => Boolean(state?.focusTrack || state?.focusBus),
  );
  // Spot (Cmd+J) types a time into the clock; "+100" / "-30" are relative to the play cursor (WP76).
  def("spot", () => app.editTime(), hasProject);
  def("time.copy", () => app.copyTime(), hasProject);
  def("nav.start", () => app.seek(0), hasProject);
  def("nav.end", () => app.seek(app.totalFrames()), hasProject);
  // The automatic "left off" marker (left-off.js): where the project was last saved or closed.
  def(
    "nav.to_resume",
    () => {
      const { leftOff } = app.getState();
      if (leftOff) app.seek(leftOff.frame);
    },
    (state) => hasProject(state) && Boolean(state.leftOff),
  );
  // Left/Right: a few pixels; Shift: 1 s (the ids "_far" are kept so user keymaps still match).
  def("nav.back", () => moveBy(-offsets().nudge)(), hasProject);
  def("nav.forward", () => moveBy(offsets().nudge)(), hasProject);
  def("nav.back_far", () => moveBy(-offsets().near)(), hasProject);
  def("nav.forward_far", () => moveBy(offsets().near)(), hasProject);
  def("nav.back_fine", () => moveBy(-offsets().fine)(), hasProject);
  def("nav.forward_fine", () => moveBy(offsets().fine)(), hasProject);
  // Tab / Shift+Tab (WP19i): the same action from the timeline's and the transcript's keys.
  for (const prefix of ["nav", "transcript"]) {
    def(`${prefix}.next_stop`, () => actions.tabStop(1), hasProject);
    def(`${prefix}.prev_stop`, () => actions.tabStop(-1), hasProject);
  }
  def("nav.tab_target_cycle", () => actions.cycleTabScope(), hasProject);
  const stepFocus = (direction) => () => {
    const state = app.getState();
    const id = stepTrack(state.project, state.focusTrack, direction);
    if (id) app.patch({ focusTrack: id, focusBus: null, rangeTracks: new Set() });
  };
  def("track.prev", stepFocus(-1), hasProject);
  def("track.next", stepFocus(1), hasProject);
  def(
    "nav.to_in",
    () => app.seek(app.getState().inPoint),
    (state) => hasProject(state) && (state.inPoint ?? null) !== null,
  );
  def(
    "nav.to_out",
    () => app.seek(app.getState().outPoint),
    (state) => hasProject(state) && (state.outPoint ?? null) !== null,
  );
  def(
    "mark.in",
    () => {
      const state = app.getState();
      app.patch({ ...setInPoint(state, state.playhead), rangeTracks: new Set() });
    },
    hasProject,
  );
  def(
    "mark.out",
    () => {
      const state = app.getState();
      app.patch({ ...setOutPoint(state, state.playhead), rangeTracks: new Set() });
    },
    hasProject,
  );
  def("mark.clear_in", () => app.patch({ inPoint: null, rangeTracks: new Set() }), hasProject);
  def("mark.clear_out", () => app.patch({ outPoint: null, rangeTracks: new Set() }), hasProject);
  def(
    "mark.clear",
    () => app.patch({ inPoint: null, outPoint: null, rangeTracks: new Set() }),
    hasProject,
  );
  def("palette.open", () => app.openPalette());
  def("help.keys", () => app.openKeys());
  def("help.open", () => app.openHelp());
  def("help.search", () => app.openSearch());
  def("keymap.import", () => app.importKeys());
  def("keymap.export", () => app.exportKeys());
  def("keymap.reset", () => app.resetKeys());
}
