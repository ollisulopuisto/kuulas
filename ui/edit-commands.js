// The editing commands: B, X, Backspace and the rest of the sheet's edit keys.
// Each one is a plan (edit-plans.js) sent through the editor; `can()` asks the same
// plan whether there is anything to do. Keys live in keymap-default.js, never here.
import {
  changedTracks,
  createBurst,
  cutPlan,
  deletePlan,
  gainPlan,
  mutePlan,
  nudgePlan,
  soloPlan,
  splitPlan,
  trackMutePlan,
  trimPlan,
} from "./edit-plans.js";
import { selectAllIds } from "./selection.js";

/**
 * `app`: getState, patch(statePatch), edit(change) (the editor's change), toast(text,
 * { undo }), now(). `t` translates, `formatSeconds(seconds)` writes a number of seconds.
 */
export function registerEditCommands(registry, { app, t, formatSeconds }) {
  const burst = createBurst();
  const def = (id, run, can) => registry.register(id, run, { can, hintKey: `cmd.${id}.hint` });
  const hasProject = (state) => Boolean(state?.project);

  function toastFor(plan, before, response) {
    if (!plan.toast) return;
    const values = { ...plan.toast.values };
    if (values.seconds !== undefined) values.seconds = formatSeconds(values.seconds);
    if (plan.toast.tracks) {
      values.count = changedTracks(before, response.project).length;
      if (values.count === 0) return app.toast(t("ui.edit.toast.nothing"), { undo: false });
    }
    app.toast(t(plan.toast.key, values), { undo: true });
  }

  function send(plan) {
    const before = app.getState().project;
    app.edit({
      op: plan.op,
      args: plan.args,
      label: t(plan.label.key),
      coalesce: plan.coalesce,
      combine: plan.combine,
      done: (response) => toastFor(plan, before, response),
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

  planned("edit.split", (s) => splitPlan(s));
  planned("edit.split_all", (s) => splitPlan(s, { all: true }));
  planned("edit.delete", deletePlan);
  planned("edit.cut", (s) => cutPlan(s));
  planned("edit.cut_track", (s) => cutPlan(s, { thisTrackOnly: true }));
  planned("clip.mute", mutePlan);
  planned("edit.trim_start", (s) => trimPlan(s, "start"));
  planned("edit.trim_end", (s) => trimPlan(s, "end"));
  planned("edit.nudge_left", (s) => nudgePlan(s, -1));
  planned("edit.nudge_right", (s) => nudgePlan(s, 1));
  planned("track.mute", trackMutePlan);
  planned("track.solo", (s) => soloPlan(s, true));
  planned("track.solo_add", (s) => soloPlan(s, false));

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
    run: () => app.patch({ selection: new Set(selectAllIds(app.getState(), allTracks)) }),
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
