// Bus roles: a bus may carry a role (speech / music) its tracks take when the role is set
// or when they are moved onto the bus. The tracks keep their own kind (a manual override
// stays), so the UI flags the ones that differ. Pure; the plans are edit-plans-style
// {op, args, label}.

import { busOfFocus } from "./bus-collapse.js";
import { currentTrack } from "./selection.js";

const plan = (op, args, key) => ({
  op,
  args,
  label: { key: `ui.edit.label.${key}` },
  toast: null,
});

const busOf = (project, id) => (project?.buses ?? []).find((bus) => bus.id === id) ?? null;

/**
 * True when the track is on a bus with a role, does not follow it (it was set by hand)
 * and its kind is another. A following track always has the bus's kind (the ops keep it so).
 */
export function roleDiffers(project, track) {
  if (!track?.bus || track.follow_bus_role) return false;
  const role = busOf(project, track.bus)?.kind;
  return Boolean(role) && track.kind !== role;
}

/** The role dropdown's choice for a track: "match" (follows its bus), else its own kind. */
export function trackRoleChoice(_project, track) {
  return track?.follow_bus_role ? "match" : (track?.kind ?? "speech");
}

/** `{ role, total, differ }` for a bus: its role, tracks on it, tracks whose kind differs. */
export function busRoleStatus(project, busId) {
  const role = busOf(project, busId)?.kind ?? null;
  const members = (project?.tracks ?? []).filter((track) => track.bus === busId);
  return {
    role,
    total: members.length,
    differ: members.filter((track) => roleDiffers(project, track)).length,
  };
}

/** Set (or with null clear) the role of the bus in focus; null when it already has it. */
export function busRolePlan(state, role) {
  const bus = busOf(state?.project, busOfFocus(state));
  if (!bus || (bus.kind ?? null) === role) return null;
  return plan("set_bus", { bus_id: bus.id, kind: role }, "bus_role");
}

const focusedTrack = (state) => {
  const id = currentTrack(state);
  return (state?.project?.tracks ?? []).find((item) => item.id === id) ?? null;
};

/** "Match bus role": the focused track follows its bus's role (needs a bus with a role). */
export function matchRolePlan(state) {
  const track = focusedTrack(state);
  if (!track || track.follow_bus_role || !busOf(state.project, track.bus)?.kind) return null;
  return plan("set_track", { track_id: track.id, follow_bus_role: true }, "match_role");
}

/** "Speech" / "Music" on the focused track: its own kind, no longer following the bus. */
export function trackRolePlan(state, kind) {
  const track = focusedTrack(state);
  if (!track || (!track.follow_bus_role && track.kind === kind)) return null;
  return plan("set_track", { track_id: track.id, kind }, "track_role");
}

/** Give every track on the focused bus its role again: one set_bus, one undo step. */
export function reapplyRolePlan(state) {
  const id = busOfFocus(state);
  const status = busRoleStatus(state?.project, id);
  if (status.role === null || status.differ === 0) return null;
  return plan("set_bus", { bus_id: id, kind: status.role }, "reapply_role");
}
