// The editing commands: B, X, Backspace and the rest of the sheet's edit keys.
// Each one is a plan (edit-plans.js) sent through the editor; `can()` asks the same
// plan whether there is anything to do. Keys live in keymap-default.js, never here.

import { busRolePlan, matchRolePlan, reapplyRolePlan, trackRolePlan } from "./bus-role.js";
import { expandGroups, groupClipsPlan, mergeClipsPlan, ungroupClipsPlan } from "./clip-groups.js";
import { CLIPBOARD_VIEWS, keepCount, pasteChoice } from "./clipboard.js";
import {
  addTrackPlan,
  busMutePlan,
  changedTracks,
  closeGapPlan,
  copyPlan,
  createBurst,
  cutPlan,
  deleteEmptyTracksPlan,
  deletePlan,
  fadePlan,
  gainPlan,
  groupBusPlan,
  liftCutPlan,
  moveTrackPlan,
  mutePlan,
  newBusPlan,
  nudgePlan,
  pasteEntry,
  pastePlan,
  quickMutePlan,
  removeClipsPlan,
  removeFromBusPlan,
  removePlan,
  resetGainsPlan,
  soloPlan,
  splitPlan,
  trackMutePlan,
  trimPlan,
  ungroupPlan,
} from "./edit-plans.js";
import { toggleScopeMode } from "./range-scope.js";
import { selectAllIds } from "./selection.js";
import { cycleKindPlan } from "./track-kind.js";

/**
 * `app`: getState, patch(statePatch), edit(change) (the editor's change), toast(text,
 * { undo }), now(), copy(body) (-> Promise: the clipboard copy), refreshClipboard().
 * `t` translates, `formatSeconds(seconds)` writes a number of seconds.
 */
export function registerEditCommands(registry, { app, t, formatSeconds }) {
  const burst = createBurst();
  const def = (id, run, can) => registry.register(id, run, { can, hintKey: `cmd.${id}.hint` });
  const hasProject = (state) => Boolean(state?.project);

  /** The edits that use up the marked range. */
  const RANGE_SPENT_OPS = new Set([
    "clipboard_cut",
    "clipboard_lift_cut",
    "ripple_delete",
    "cut_range",
  ]);

  /** The edits that close the gap: they leave a splice at the start of the range. */
  const RIPPLE_OPS = new Set(["clipboard_cut", "ripple_delete", "cut_range"]);

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
    // Undo brings back the marks this edit is about to use up (range-memory.js).
    if (RANGE_SPENT_OPS.has(plan.op)) app.rememberRange?.();
    app.edit({
      op: plan.op,
      args: plan.args,
      label: t(plan.label.key),
      coalesce: plan.coalesce,
      combine: plan.combine,
      provisional: plan.provisional,
      done: (response) => {
        toastFor(plan, before, response);
        // The range is spent: its marks and the selection would only be left drawn on the
        // timeline (owner, 2026-10-18). Soft delete keeps them: the gap is still the range.
        // A ripple cut leaves a splice at the range's start: the cursor goes there, so P (play from
        // before the cursor) plays the join (owner, 2026-10-18). Lift-cut leaves a gap, not a splice.
        if (RIPPLE_OPS.has(plan.op) && Number.isFinite(plan.args?.start)) {
          app.seek?.(plan.args.start);
        }
        if (RANGE_SPENT_OPS.has(plan.op)) {
          app.patch({
            inPoint: null,
            outPoint: null,
            rangeTracks: new Set(),
            selection: new Set(),
          });
        }
        // A cut adds an entry; a paste may follow a rename elsewhere: look again.
        if (plan.op.startsWith("clipboard_")) app.refreshClipboard?.();
      },
    });
  }

  /** A range command with "selected tracks only" and no track selected says why it did nothing. */
  const refuse = (plan) => app.toast(t(plan.refuse.key), { undo: false });

  /** Register `id` as "send the plan this builds from the state". */
  const planned = (id, build) =>
    def(
      id,
      () => {
        const plan = build(app.getState());
        if (plan?.refuse) refuse(plan);
        else if (plan) send(plan);
      },
      (state) => build(state) !== null,
    );

  planned("edit.group", groupClipsPlan);
  planned("edit.ungroup", ungroupClipsPlan);
  planned("edit.merge", mergeClipsPlan);
  planned("edit.split", (s) => splitPlan(s));
  planned("edit.split_all", (s) => splitPlan(s, { all: true }));
  planned("edit.delete", deletePlan);
  planned("edit.remove_clips", removeClipsPlan);
  planned("track.add", (s) => addTrackPlan(s, "speech", { t }));
  planned("track.delete_empty", deleteEmptyTracksPlan);
  planned("track.reset_gains", resetGainsPlan);
  planned("track.add_music", (s) => addTrackPlan(s, "music", { t }));
  planned("edit.remove", (s) => removePlan(s));
  planned("edit.remove_track", (s) => removePlan(s, { thisTrackOnly: true }));
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
      if (plan.refuse) return refuse(plan);
      void app.copy(plan.body).then((ok) => {
        if (ok) app.toast(t(plan.toast.key, plan.toast.values), { undo: false });
      });
    },
    (s) => copyPlan(s, t) !== null,
  );
  // Play-preview of the picked (else newest) entry: a temporary project on the server, so
  // no edit, no undo step and the real project is not touched.
  def(
    "edit.preview_clipboard",
    () => {
      const entry = pasteEntry(app.getState());
      if (!entry) return;
      void app.previewClipboard(entry.id).then((answer) => {
        if (answer && !answer.started) {
          app.toast(t("ui.clipboard.preview_nothing"), { undo: false });
        }
      });
    },
    (s) => hasProject(s) && pasteEntry(s) !== null,
  );
  // The only way entries leave the clipboard besides deleting one by hand (WP65): keep the
  // newest N of this project's, N from the Clipboard tab's field (100 by default).
  def(
    "edit.clear_old_clipboard",
    () => void app.clearOldClipboard(keepCount(app.getState())),
    (s) => hasProject(s) && (s.clipboard?.length ?? 0) > 0,
  );
  // The Share star of the picked (else newest) entry: marked entries show in the Shared view
  // of every project (WP65). Not an edit: the clipboard is not project state.
  def(
    "edit.share_clipboard",
    () => {
      const entry = pasteEntry(app.getState());
      if (entry) void app.shareClipboard(entry.id, !entry.shared);
    },
    (s) => hasProject(s) && pasteEntry(s) !== null,
  );
  // The tab's three views and the picker for any project's clipboard.
  for (const view of CLIPBOARD_VIEWS) {
    def(
      `clipboard.view_${view}`,
      () => app.showClipboard(view),
      (s) => hasProject(s),
    );
  }
  def(
    "clipboard.open_project",
    () => app.openClipboardProject(),
    (s) => hasProject(s),
  );
  planned("edit.paste", (s) => pastePlan(s, { mode: "insert", target: pasteChoice(s).target }));
  planned("edit.paste_overwrite", (s) =>
    pastePlan(s, { mode: "overwrite", target: pasteChoice(s).target }),
  );
  planned("edit.paste_track", (s) => pastePlan(s, { mode: "insert", target: "current" }));
  // The other two of the four paste forms, fixed whatever the panel's choice says: insert on
  // the entry's own tracks, overwrite on the current track. Menu and palette, no keys.
  planned("edit.paste_same", (s) => pastePlan(s, { mode: "insert", target: "same" }));
  planned("edit.paste_overwrite_track", (s) =>
    pastePlan(s, { mode: "overwrite", target: "current" }),
  );
  planned("clip.mute", mutePlan);
  planned("clip.quick_mute", quickMutePlan);
  planned("clip.fade", fadePlan);
  planned("edit.trim_start", (s) => trimPlan(s, "start"));
  planned("edit.trim_end", (s) => trimPlan(s, "end"));
  planned("edit.nudge_left", (s) => nudgePlan(s, -1));
  planned("edit.nudge_right", (s) => nudgePlan(s, 1));
  planned("edit.move_up", (s) => moveTrackPlan(s, -1));
  planned("edit.move_down", (s) => moveTrackPlan(s, 1));
  planned("track.mute", trackMutePlan);
  planned("track.solo", (s) => soloPlan(s, true));
  planned("track.solo_add", (s) => soloPlan(s, false));
  planned("track.cycle_kind", cycleKindPlan);
  planned("bus.mute", busMutePlan);
  planned("bus.ungroup", ungroupPlan);
  planned("bus.role_speech", (s) => busRolePlan(s, "speech"));
  planned("bus.role_music", (s) => busRolePlan(s, "music"));
  planned("bus.role_none", (s) => busRolePlan(s, null));
  planned("bus.reapply_role", reapplyRolePlan);
  planned("track.match_role", matchRolePlan);
  planned("track.role_speech", (s) => trackRolePlan(s, "speech"));
  planned("track.role_music", (s) => trackRolePlan(s, "music"));
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

  // E, the Edit menu item and the status chip: all tracks <-> selected tracks only (WP83).
  def("range.scope_toggle", () => app.patch(toggleScopeMode(app.getState())), hasProject);
}
