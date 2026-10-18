// The commands the editor can do today, registered by id (ids from keymap-default.js).
// Everything else in the keymap is "planned" until its work package lands.
import { canRestore } from "./history-model.js";

/** The next or previous track's id; stops at the ends; null without a project. */
export function stepTrack(project, current, direction) {
  const tracks = project?.tracks ?? [];
  if (tracks.length === 0) return null;
  const at = tracks.findIndex((track) => track.id === current);
  if (at < 0) return direction > 0 ? tracks[0].id : tracks[tracks.length - 1].id;
  return tracks[Math.min(tracks.length - 1, Math.max(0, at + direction))].id;
}

/** Playhead steps in frames: 1 s, 5 s (Shift) and 10 ms (Alt). */
export function seekOffsets(rate) {
  return { near: rate, far: rate * 5, fine: Math.round(rate / 100) };
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
  const offsets = () => seekOffsets(rate());

  def("transport.play", () => actions.togglePlay());
  def(
    "transport.play_before",
    () => actions.playFrom(prerollStart(app.getState().playhead ?? 0, rate())),
    hasProject,
  );
  def("transport.shuttle_forward", () => actions.shuttle("l"), hasProject);
  def("transport.shuttle_back", () => actions.shuttle("j"), hasProject);
  def("transport.shuttle_stop", () => actions.shuttle("k"), hasProject);
  def("transport.speed", () => actions.fastListening(), hasProject);
  def("nav.home", () => actions.goHome());
  def("panel.next", () => actions.cyclePanel(1));
  def("panel.previous", () => actions.cyclePanel(-1));
  def("view.toggle", () => actions.toggleView(), hasProject);
  def("view.fit", () => actions.fitView(), hasProject);
  def("view.fit_selection", () => actions.fitSelection(), hasProject);
  def("view.back", () => actions.viewBack(), hasProject);
  def("view.reset_remembered", () => actions.resetRememberedView(), hasProject);
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
  def("gate.open_stretch", () => app.openGateStretch(), hasProject);
  def(
    "rename",
    () => app.focusName(),
    (state) => Boolean(state?.focusTrack || state?.focusBus),
  );
  def("nav.start", () => app.seek(0), hasProject);
  def("nav.end", () => app.seek(app.totalFrames()), hasProject);
  def("nav.back", () => moveBy(-offsets().near)(), hasProject);
  def("nav.forward", () => moveBy(offsets().near)(), hasProject);
  def("nav.back_far", () => moveBy(-offsets().far)(), hasProject);
  def("nav.forward_far", () => moveBy(offsets().far)(), hasProject);
  def("nav.back_fine", () => moveBy(-offsets().fine)(), hasProject);
  def("nav.forward_fine", () => moveBy(offsets().fine)(), hasProject);
  const stepFocus = (direction) => () => {
    const state = app.getState();
    const id = stepTrack(state.project, state.focusTrack, direction);
    if (id) app.patch({ focusTrack: id, focusBus: null });
  };
  def("track.prev", stepFocus(-1), hasProject);
  def("track.next", stepFocus(1), hasProject);
  def("mark.in", () => app.patch({ inPoint: app.getState().playhead }), hasProject);
  def("mark.out", () => app.patch({ outPoint: app.getState().playhead }), hasProject);
  def("mark.clear_in", () => app.patch({ inPoint: null }), hasProject);
  def("mark.clear_out", () => app.patch({ outPoint: null }), hasProject);
  def("mark.clear", () => app.patch({ inPoint: null, outPoint: null }), hasProject);
  def("palette.open", () => app.openPalette());
  def("help.keys", () => app.openKeys());
  def("help.open", () => app.openHelp());
  def("keymap.import", () => app.importKeys());
  def("keymap.export", () => app.exportKeys());
  def("keymap.reset", () => app.resetKeys());
}
