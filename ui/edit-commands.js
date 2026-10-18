// The editing commands: B, X, Backspace and the rest of the sheet's edit keys.
// Each one is a plan (edit-plans.js) sent through the editor; `can()` asks the same
// plan whether there is anything to do. Keys live in keymap-default.js, never here.
import { expandGroups, groupClipsPlan, mergeClipsPlan, ungroupClipsPlan } from "./clip-groups.js";
import { pasteChoice } from "./clipboard.js";
import {
  busMutePlan,
  changedTracks,
  closeGapPlan,
  copyPlan,
  createBurst,
  cutPlan,
  deletePlan,
  fadePlan,
  gainPlan,
  groupBusPlan,
  liftCutPlan,
  mutePlan,
  newBusPlan,
  nudgePlan,
  pastePlan,
  removeFromBusPlan,
  soloPlan,
  splitPlan,
  trackMutePlan,
  trimPlan,
  ungroupPlan,
} from "./edit-plans.js";
import { selectAllIds } from "./selection.js";

/**
 * `app`: getState, patch(statePatch), edit(change) (the editor's change), toast(text,
 * { undo }), now(), copy(body) (-> Promise: the clipboard copy), refreshClipboard().
 * `t` translates, `formatSeconds(seconds)` writes a number of seconds.
 */
export function registerEditCommands(registry, { app, t, formatSeconds }) {
  const burst = createBurst();
  const def = (id, run, can) => registry.register(id, run, { can, hintKey: `cmd.${id}.hint` });
  const hasProject = (state) => Boolean(state?.project);

  function toastFor(plan, before, response) {
    if (!plan.toast) return;
    // A plan may change its message once the answer is in: a cut whose clipboard copy
    // failed, a paste that lacked recordings (edit-plans.js).
    const variant = plan.toast.variant?.(response) ?? null;
    const values = { ...plan.toast.values, ...variant?.values };
    if (values.seconds !== undefined) values.seconds = formatSeconds(values.seconds);
    if (plan.toast.tracks) {
      values.count = changedTracks(before, response.project).length;
      if (values.count === 0) return app.toast(t("ui.edit.toast.nothing"), { undo: false });
    }
    app.toast(t(variant?.key ?? plan.toast.key, values), { undo: variant?.undo !== false });
  }

  function send(plan) {
    const before = app.getState().project;
    app.edit({
      op: plan.op,
      args: plan.args,
      label: t(plan.label.key),
      coalesce: plan.coalesce,
      combine: plan.combine,
      done: (response) => {
        toastFor(plan, before, response);
        // A cut adds an entry; a paste may follow a rename elsewhere: look again.
        if (plan.op.startsWith("clipboard_")) app.refreshClipboard?.();
      },
    });
  }

  /** Register `id` as "send the plan this builds from the state". */
  const planned = (id, build) =>
    def(
      id,
      () => {
        const plan = build(app.getState());
        if (plan) send(plan);
      },
      (state) => build(state) !== null,
    );

  planned("edit.group", groupClipsPlan);
  planned("edit.ungroup", ungroupClipsPlan);
  planned("edit.merge", mergeClipsPlan);
  planned("edit.split", (s) => splitPlan(s));
  planned("edit.split_all", (s) => splitPlan(s, { all: true }));
  planned("edit.delete", deletePlan);
  planned("edit.cut", (s) => cutPlan(s, { t }));
  planned("edit.cut_track", (s) => cutPlan(s, { thisTrackOnly: true, t }));
  planned("edit.lift_cut", (s) => liftCutPlan(s, { t }));
  planned("edit.close_gap_all", closeGapPlan);

  // The clipboard (WP46). Mod+C copies and changes nothing in the project. The paste keys
  // all use the newest entry (or the one picked in the Clipboard tab) at the play cursor:
  // Mod+V inserts, Alt+Mod+V overwrites, both on the tracks the panel's choice names
  // (the entry's own tracks unless "current track" is chosen); Shift+Mod+V inserts on
  // the current track whatever the choice.
  def(
    "edit.copy",
    () => {
      const plan = copyPlan(app.getState(), t);
      if (!plan) return;
      void app.copy(plan.body).then((ok) => {
        if (ok) app.toast(t(plan.toast.key, plan.toast.values), { undo: false });
      });
    },
    (s) => copyPlan(s, t) !== null,
  );
  planned("edit.paste", (s) => pastePlan(s, { mode: "insert", target: pasteChoice(s).target }));
  planned("edit.paste_overwrite", (s) =>
    pastePlan(s, { mode: "overwrite", target: pasteChoice(s).target }),
  );
  planned("edit.paste_track", (s) => pastePlan(s, { mode: "insert", target: "current" }));
  planned("clip.mute", mutePlan);
  planned("clip.fade", fadePlan);
  planned("edit.trim_start", (s) => trimPlan(s, "start"));
  planned("edit.trim_end", (s) => trimPlan(s, "end"));
  planned("edit.nudge_left", (s) => nudgePlan(s, -1));
  planned("edit.nudge_right", (s) => nudgePlan(s, 1));
  planned("track.mute", trackMutePlan);
  planned("track.solo", (s) => soloPlan(s, true));
  planned("track.solo_add", (s) => soloPlan(s, false));
  planned("bus.mute", busMutePlan);
  planned("bus.ungroup", ungroupPlan);
  planned("track.remove_from_bus", removeFromBusPlan);

  // Creating a bus: once the server has answered, the new one (always the last) gets the
  // focus and its name field (F2's), so naming it is the next thing typed.
  const plannedBus = (id, build) =>
    def(
      id,
      () => {
        const plan = build(app.getState());
        if (!plan) return;
        app.edit({
          op: plan.op,
          args: plan.args,
          label: t(plan.label.key),
          done: (response) => {
            const created = response?.project?.buses?.at(-1);
            if (!created) return;
            app.patch({ focusBus: created.id, focusTrack: null });
            app.focusName();
          },
        });
      },
      (state) => build(state) !== null,
    );
  plannedBus("track.group_into_bus", groupBusPlan);
  plannedBus("track.new_bus", newBusPlan);

  // Gain's key is read when the key is pressed, so a pause starts a new undo step.
  const gain = (direction) => (s) => gainPlan(s, direction, burst.key(app.now()));
  for (const [id, direction] of [
    ["clip.gain_up", 1],
    ["clip.gain_down", -1],
  ]) {
    def(
      id,
      () => {
        const plan = gain(direction)(app.getState());
        if (plan) send(plan);
      },
      // `can` must not start a burst: ask with a fixed key.
      (s) => gainPlan(s, direction, "can") !== null,
    );
  }

  const selectAll = (allTracks) => ({
    run: () => {
      const state = app.getState();
      app.patch({ selection: expandGroups(state.project, selectAllIds(state, allTracks)) });
    },
    can: (s) => selectAllIds(s, allTracks).length > 0,
  });
  def("edit.select_all_track", selectAll(false).run, selectAll(false).can);
  def("edit.select_all", selectAll(true).run, selectAll(true).can);

  def(
    "group.toggle",
    () => app.patch({ groupEditing: app.getState().groupEditing === false }),
    hasProject,
  );
}
