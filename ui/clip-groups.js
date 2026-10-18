// Clip groups and merge: what the selection means for a group, and the three plans
// (group, ungroup, merge). Pure functions of the store's state, so `can()` and the edit
// agree and node tests cover them. The edits themselves are ops.py's group_clips,
// ungroup_clips and merge_clips; `canJoin` mirrors join.py's `_can_join` so the toast can
// say beforehand what merge will do.
import { selectedClips } from "./selection.js";

const clipsOf = (project) => (project?.tracks ?? []).flatMap((track) => track.clips ?? []);

/** `ids` plus every clip sharing a group with one of them (a group is one unit). */
export function expandGroups(project, ids) {
  const wanted = new Set(ids);
  const groups = new Set();
  for (const clip of clipsOf(project))
    if (wanted.has(clip.id) && clip.group) groups.add(clip.group);
  if (groups.size === 0) return wanted;
  for (const clip of clipsOf(project)) if (groups.has(clip.group)) wanted.add(clip.id);
  return wanted;
}

/** Shift/Mod-click on a clip: add it with its group, or remove it with its group. */
export function toggleGroupSelection(project, selection, id) {
  const unit = expandGroups(project, [id]);
  const next = new Set(selection);
  if (selection.has(id)) for (const member of unit) next.delete(member);
  else for (const member of unit) next.add(member);
  return next;
}

/** join.py's `_can_join` for two clips of one track, `a` before `b`. */
function canJoin(a, b) {
  return (
    a.media === b.media &&
    a.offset + a.length === b.offset &&
    a.start + a.length === b.start &&
    a.gain_db === b.gain_db &&
    a.pan === b.pan &&
    a.muted === b.muted &&
    (a.group ?? null) === (b.group ?? null) &&
    (a.envelope ?? []).length === 0 &&
    (b.envelope ?? []).length === 0 &&
    !a.xfade_out &&
    !b.xfade_in
  );
}

/**
 * What merge does to `ids`: { merged, into, left } = clips joined, the clips they become,
 * and selected clips that could not join anything.
 */
export function mergeSummary(project, ids) {
  let merged = 0;
  let into = 0;
  let total = 0;
  for (const track of project?.tracks ?? []) {
    const picked = (track.clips ?? []).filter((clip) => ids.has(clip.id));
    picked.sort((a, b) => a.start - b.start);
    total += picked.length;
    let run = 0;
    const close = () => {
      if (run > 1) {
        merged += run;
        into += 1;
      }
    };
    for (const [index, clip] of picked.entries()) {
      if (index > 0 && canJoin(picked[index - 1], clip)) run += 1;
      else {
        close();
        run = 1;
      }
    }
    close();
  }
  return { merged, into, left: total - merged };
}

const plan = (op, ids, key, toast) => ({
  op,
  args: { clip_ids: ids },
  label: { key: `ui.edit.label.${key}` },
  toast,
});

const idsOf = (state) => selectedClips(state).map((entry) => entry.clip.id);

/** Group the selected clips: two or more, and not already exactly one group. */
export function groupClipsPlan(state) {
  const chosen = selectedClips(state).map((entry) => entry.clip);
  if (chosen.length < 2) return null;
  const first = chosen[0].group;
  if (first && chosen.every((clip) => clip.group === first)) {
    const members = clipsOf(state.project).filter((clip) => clip.group === first);
    if (members.length === chosen.length) return null;
  }
  return plan("group_clips", idsOf(state), "group_clips", {
    key: "ui.edit.toast.group_clips",
    values: { count: chosen.length },
  });
}

/** Dissolve the groups of the selected clips. */
export function ungroupClipsPlan(state) {
  const chosen = selectedClips(state).map((entry) => entry.clip);
  if (!chosen.some((clip) => clip.group)) return null;
  const groups = new Set(chosen.map((clip) => clip.group).filter(Boolean));
  return plan("ungroup_clips", idsOf(state), "ungroup_clips", {
    key: "ui.edit.toast.ungroup_clips",
    values: { count: groups.size },
  });
}

/** Merge the selected clips that touch: lossless, split at the old boundary undoes it. */
export function mergeClipsPlan(state) {
  const ids = idsOf(state);
  if (ids.length < 2) return null;
  const summary = mergeSummary(state.project, new Set(ids));
  if (summary.merged === 0) return null;
  const key = summary.left === 0 ? "merge" : "merge_partial";
  return plan("merge_clips", ids, "merge_clips", {
    key: `ui.edit.toast.${key}`,
    values: { count: summary.merged, into: summary.into, left: summary.left },
  });
}
