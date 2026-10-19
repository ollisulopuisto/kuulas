// The sync commands (R51, WP19a): U frees the selected clips from sync (or links them again),
// R / Alt+Mod+R resyncs the selection, Shift+Alt+Mod+R resyncs from the play cursor on, and the
// Markers tab's list of drifting clips has Resync all, Free all and ] / [ to step through it.
// Nothing here resyncs by itself: every command is something the user asked for. Keys are in
// keymap-default.js, the list is the Markers tab.
import { driftRows, stepDrift } from "./sync-state.js";

const hasProject = (state) => Boolean(state?.project);
const selected = (state) => [...(state?.selection ?? [])];

function clipsById(state) {
  const found = new Map();
  for (const track of state?.project?.tracks ?? []) {
    for (const clip of track.clips) found.set(clip.id, clip);
  }
  return found;
}

/** Will U free these (some are still linked) or link them again (all are free already)? */
export function freeing(state, ids) {
  const clips = clipsById(state);
  return ids.some((id) => clips.get(id)?.free !== true);
}

/**
 * `app`: getState, patch(statePatch), edit(change), toast(text, { undo }), seek(frame),
 * syncCommand(name, args) (a server command that answers with the resync report; resolves when the
 * state is applied). `t` translates.
 */
export function registerSyncCommands(registry, { app, t }) {
  const def = (id, run, can) => registry.register(id, run, { can, hintKey: `cmd.${id}.hint` });
  const drifting = (state) => driftRows(state?.syncClips);

  function setFree(ids, free, label, message) {
    app.edit({
      op: "set_free",
      args: { clip_ids: ids, free },
      label: t(label),
      done: () => app.toast(t(message, { count: ids.length }), { undo: true }),
    });
  }

  def(
    "sync.free",
    () => {
      const state = app.getState();
      const ids = selected(state);
      if (ids.length === 0) return;
      const free = freeing(state, ids);
      setFree(
        ids,
        free,
        free ? "ui.sync.history.free" : "ui.sync.history.link",
        free ? "ui.sync.toast.freed" : "ui.sync.toast.linked",
      );
    },
    (state) => hasProject(state) && selected(state).length > 0,
  );

  def(
    "sync.resync",
    () => {
      const ids = selected(app.getState());
      if (ids.length > 0) void app.syncCommand("resync", { clip_ids: ids });
    },
    (state) => hasProject(state) && selected(state).length > 0,
  );

  def(
    "sync.resync_end",
    () => void app.syncCommand("resync_from", { frame: app.getState().playhead }),
    hasProject,
  );

  def(
    "sync.resync_all",
    () => {
      const ids = drifting(app.getState()).map((row) => row.clip_id);
      if (ids.length > 0) void app.syncCommand("resync", { clip_ids: ids });
    },
    (state) => hasProject(state) && drifting(state).length > 0,
  );

  def(
    "sync.free_all",
    () => {
      const ids = drifting(app.getState()).map((row) => row.clip_id);
      if (ids.length > 0) {
        setFree(ids, true, "ui.sync.history.free_all", "ui.sync.toast.freed");
      }
    },
    (state) => hasProject(state) && drifting(state).length > 0,
  );

  const step = (direction) => () => {
    const state = app.getState();
    const row = stepDrift(drifting(state), state.playhead, direction);
    if (!row) return;
    app.seek(row.start);
    app.patch({ selection: new Set([row.clip_id]) });
  };
  def("sync.drift_next", step(1), (state) => hasProject(state) && drifting(state).length > 0);
  def("sync.drift_previous", step(-1), (state) => hasProject(state) && drifting(state).length > 0);
}
