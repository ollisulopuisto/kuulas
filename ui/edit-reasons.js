// Why an edit key did nothing (owner, 2026-10-21: "edit keys never fail silently"). A plan that
// is null (edit-plans.js) means "nothing to do"; the key then shows one line saying why, instead
// of a silent no-op or the OS beep. Pure: `idleReason(id, state)` is asked only when the command
// cannot act (commands.js `why`), so each reason below is the answer to "what is missing".
// Texts are message keys under ui.edit.idle.* (en + fi). A refusal the plan itself makes (no tracks
// selected, the stretch is muted already) never gets here: that plan is not null.

import { pasteChoice } from "./clipboard.js";
import { pasteAnchor, pasteEntry } from "./edit-plans.js";
import { editTarget } from "./intent.js";
import { selectedClips } from "./selection.js";

const reason = (name) => ({ key: `ui.edit.idle.${name}` });
const fixed = (name) => () => reason(name);

/** What is missing, per command: (state) -> { key } . Ids not listed fall back to "generic". */
const REASONS = {
  "edit.remove": fixed("remove"),
  "edit.remove_track": fixed("remove"),
  "edit.cut": fixed("cut"),
  "edit.cut_track": fixed("cut"),
  "edit.lift_cut": fixed("cut"),
  "edit.close_gap_all": fixed("close_gap"),
  "edit.remove_clips": fixed("remove_clips"),
  "edit.delete": (state) =>
    // Clips are selected, so they must all be muted already.
    reason(selectedClips(state).length > 0 ? "delete_muted" : "delete"),
  "edit.copy": (state) => reason(editTarget(state) === null ? "copy" : "copy_empty"),
  "edit.split": fixed("split"),
  "edit.split_all": fixed("split_all"),
  "edit.trim_start": fixed("trim"),
  "edit.trim_end": fixed("trim"),
  "clip.fade": fixed("fade"),
  "clip.quick_mute": fixed("quick_mute"),
  "clip.mute": fixed("mute"),
  "edit.nudge_left": fixed("nudge"),
  "edit.nudge_right": fixed("nudge"),
  "clip.gain_up": fixed("gain"),
  "clip.gain_down": fixed("gain"),
  "edit.move_up": (state) => reason(selectedClips(state).length === 0 ? "move" : "move_first"),
  "edit.move_down": (state) => reason(selectedClips(state).length === 0 ? "move" : "move_last"),
  "edit.group": fixed("group"),
  "edit.ungroup": fixed("ungroup"),
  "edit.merge": fixed("merge"),
  "track.mute": fixed("no_track"),
  "clip.envelope_delete_point": fixed("no_point"),
  "clip.envelope_reset": fixed("no_line"),
  "track.automation_delete_point": fixed("no_point"),
  "track.automation_clear": fixed("no_duck"),
  "track.move_up": fixed("no_track"),
  "track.move_down": fixed("no_track"),
  "track.solo": fixed("no_track"),
  "track.solo_add": fixed("no_track"),
  "edit.select_all": fixed("select_all"),
  "edit.select_all_track": (state) =>
    reason(state?.focusTrack || state?.focusBus ? "select_all" : "no_track"),
};

/** The paste commands: nothing to paste, or no track to paste on. */
const pasteReason = (target) => (state) => {
  if (pasteEntry(state) === null) return reason("paste_empty");
  const needsTrack = (target ?? pasteChoice(state).target) === "current";
  return reason(needsTrack && pasteAnchor(state) === null ? "paste_no_track" : "generic");
};
for (const id of ["edit.paste", "edit.paste_insert"]) REASONS[id] = pasteReason();
for (const id of ["edit.paste_track", "edit.paste_insert_track"]) {
  REASONS[id] = pasteReason("current");
}
for (const id of ["edit.paste_same", "edit.paste_insert_same"]) REASONS[id] = pasteReason("same");

/** The commands with a reason of their own (the ones with default keys; the rest say "generic"). */
export const EDIT_KEY_IDS = new Set(Object.keys(REASONS));

/**
 * Why `id` cannot act on `state`: { key } (a message key under ui.edit.idle.*). Asked only when
 * the command's own `can` said no. Never null: an unexplained command says "generic".
 */
export function idleReason(id, state) {
  if (!state?.project) return reason("no_project");
  return REASONS[id]?.(state) ?? reason("generic");
}
