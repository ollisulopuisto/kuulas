// The sync commands (R51, WP19a): U frees the selected clips from sync (or links them again),
// R / Alt+Mod+R resyncs the selection, Shift+Alt+Mod+R resyncs from the play cursor on, and the
// Markers tab's list of drifting clips has Resync all, Free all and ] / [ to step through it.
// Nothing here resyncs by itself: every command is something the user asked for. Keys are in
// keymap-default.js, the list is the Markers tab.
// Sync asks first (owner, 2026-10-19): a command that MOVES clips (re-sync, re-sync from the cursor,
// re-sync all, send home) first asks the server what it would do (a preview that changes nothing),
// shows it in a confirm dialog, and only then applies it as one undo step. Nothing to move: a
// notice, no dialog. Freeing moves nothing and stays instant. "Confirm before re-syncing" (View)
// switches the dialog off.
import { driftRows, stepDrift } from "./sync-state.js";

const hasProject = (state) => Boolean(state?.project);

const groupOf = (project, mediaId) =>
  project.sync_groups?.find((group) => mediaId in group.members) ?? null;

/** The selected clips that sit on a different track from the one they came from. */
function movedAway(state) {
  const ids = new Set(state?.selection ?? []);
  const out = [];
  for (const track of state?.project?.tracks ?? []) {
    for (const clip of track.clips) {
      if (ids.has(clip.id) && clip.home && clip.home !== track.id) out.push(clip.id);
    }
  }
  return out;
}
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
 * state is applied), syncPreview(name, args) (what it would move, or null when the server refused),
 * confirmSync(preview) (the dialog; resolves true on Confirm), confirmEnabled() (the preference),
 * notice(text), toggleConfirmSync(). `t` translates.
 */
export function registerSyncCommands(registry, { app, t }) {
  const def = (id, run, can) => registry.register(id, run, { can, hintKey: `cmd.${id}.hint` });
  const drifting = (state) => driftRows(state?.syncClips);

  /** Preview, ask, then `apply()`: the one path of every command that moves clips. */
  async function askThen(name, args, apply) {
    if (!app.confirmEnabled()) {
      apply();
      return;
    }
    const preview = await app.syncPreview(name, args);
    if (!preview) return;
    if (preview.kind !== "move") {
      app.notice(preview.message);
      return;
    }
    if (await app.confirmSync(preview)) apply();
  }
  const resyncThen = (name, args) => askThen(name, args, () => app.syncCommand(name, args));

  // A preference, not an edit: whether the commands above show their dialog first.
  def("sync.confirm", () => app.toggleConfirmSync());

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

  const trackName = (state, clipId) =>
    state.project.tracks.find((track) => track.clips.some((c) => c.id === clipId))?.name ?? "";

  // Y: the selected clips are in sync as they sit now; the first selected is the anchor.
  def(
    "sync.mark",
    () => {
      const state = app.getState();
      const ids = selected(state);
      if (ids.length < 2) return;
      app.edit({
        op: "mark_in_sync",
        args: { clip_ids: ids, main: ids[0], basis: "timeline" },
        label: t("ui.sync.history.mark"),
        done: () =>
          app.toast(t("ui.sync.toast.marked", { name: trackName(state, ids[0]) }), { undo: true }),
      });
    },
    (state) => hasProject(state) && selected(state).length >= 2,
  );

  // Makes the first selected clip's recording the anchor; nothing moves.
  def(
    "sync.set_anchor",
    () => {
      const state = app.getState();
      const [id] = selected(state);
      if (!id) return;
      app.edit({
        op: "set_sync_anchor",
        args: { clip_id: id },
        label: t("ui.sync.history.anchor"),
        done: () =>
          app.toast(t("ui.sync.toast.anchor", { name: trackName(state, id) }), { undo: true }),
      });
    },
    (state) => {
      if (!hasProject(state)) return false;
      const [id] = selected(state);
      const clip = id ? clipsById(state).get(id) : null;
      const group = clip ? groupOf(state.project, clip.media) : null;
      return Boolean(group) && group.main !== clip.media;
    },
  );

  // Time stays; the clips go back to the track they were dragged away from.
  def(
    "sync.send_home",
    () => {
      const ids = movedAway(app.getState());
      if (ids.length === 0) return;
      void askThen("send_home", { clip_ids: ids }, () =>
        app.edit({
          op: "send_home",
          args: { clip_ids: ids },
          label: t("ui.sync.history.send_home"),
          done: () =>
            app.toast(t("ui.sync.toast.sent_home", { count: ids.length }), { undo: true }),
        }),
      );
    },
    (state) => hasProject(state) && movedAway(state).length > 0,
  );

  def(
    "sync.resync",
    () => {
      const ids = selected(app.getState());
      if (ids.length > 0) void resyncThen("resync", { clip_ids: ids });
    },
    (state) => hasProject(state) && selected(state).length > 0,
  );

  def(
    "sync.resync_end",
    () => void resyncThen("resync_from", { frame: app.getState().playhead }),
    hasProject,
  );

  def(
    "sync.resync_all",
    () => {
      const ids = drifting(app.getState()).map((row) => row.clip_id);
      if (ids.length > 0) void resyncThen("resync", { clip_ids: ids });
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
