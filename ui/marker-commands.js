// The marker commands (WP19h): M adds a marker at the playhead, Alt+M turns the in-out range
// into a region, Next/Previous move the playhead between markers, Delete removes the one
// under the playhead (or the one picked in the Markers tab). Each is one undoable edit with a
// toast that offers Undo. Keys are in keymap-default.js, the list is the Markers tab.
import { adjacentMarker, markerAt, nextMarkerName, regionFromRange } from "./markers-model.js";

const hasProject = (state) => Boolean(state?.project);
const markersOf = (state) => state?.project?.markers ?? [];

/** A fresh id; the server accepts any unused one (ops.add_marker makes its own for null). */
export function newMarkerId(random = Math.random) {
  return `k${random().toString(16).slice(2, 12).padEnd(10, "0")}`;
}

/** The marker Delete takes: the one picked in the tab, else the one starting at the playhead. */
export function deleteTarget(state) {
  const markers = markersOf(state);
  const picked = markers.find((marker) => marker.id === state.markerSelected);
  return picked ?? markerAt(markers, state.playhead);
}

/**
 * `app`: getState, patch(statePatch), edit(change), toast(text, { undo }), seek(frame),
 * recordingFrame() (the take's place on the timeline while recording, else null).
 * `t` translates.
 */
export function registerMarkerCommands(registry, { app, t, makeId = newMarkerId }) {
  // While a take records, "now" is where the take is on the timeline, not the playhead
  // (app.recordingFrame, from the record view; null when nothing records).
  const nowFrame = (state) => app.recordingFrame?.() ?? state.playhead;
  const def = (id, run, can) => registry.register(id, run, { can, hintKey: `cmd.${id}.hint` });

  function add(kind, start, end, label) {
    const state = app.getState();
    const name = nextMarkerName(markersOf(state), t(`ui.markers.default.${kind}`));
    const markerId = makeId();
    const args = { marker_id: markerId, name, start, kind };
    if (end !== null) args.end = end;
    app.edit({
      op: "add_marker",
      args,
      label: t(label),
      done: () => {
        app.patch({ markerSelected: markerId });
        app.toast(t("ui.markers.added", { name }), { undo: true });
      },
    });
  }

  def(
    "marker.add",
    () => add("marker", nowFrame(app.getState()), null, "ui.markers.history.add"),
    (state) => hasProject(state) && markerAt(markersOf(state), nowFrame(state)) === null,
  );

  def(
    "region.from_selection",
    () => {
      const { inPoint, outPoint } = app.getState();
      const range = regionFromRange(inPoint, outPoint);
      if (range) add("region", range.start, range.end, "ui.markers.history.add_region");
    },
    (state) => hasProject(state) && regionFromRange(state.inPoint, state.outPoint) !== null,
  );

  const step = (direction) => () => {
    const state = app.getState();
    const target = adjacentMarker(markersOf(state), state.playhead, direction);
    if (target) {
      app.jump(target.start);
      app.patch({ markerSelected: target.id });
    }
  };
  const canStep = (direction) => (state) =>
    hasProject(state) && adjacentMarker(markersOf(state), state.playhead, direction) !== null;
  def("marker.next", step(1), canStep(1));
  def("marker.prev", step(-1), canStep(-1));

  def(
    "marker.delete",
    () => {
      const target = deleteTarget(app.getState());
      if (!target) return;
      app.edit({
        op: "delete_marker",
        args: { marker_id: target.id },
        label: t("ui.markers.history.delete"),
        done: () => {
          if (app.getState().markerSelected === target.id) app.patch({ markerSelected: null });
          app.toast(t("ui.markers.deleted", { name: target.name }), { undo: true });
        },
      });
    },
    (state) => hasProject(state) && deleteTarget(state) !== null,
  );
}
