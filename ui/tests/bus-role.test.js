import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  busRolePlan,
  busRoleStatus,
  matchRolePlan,
  reapplyRolePlan,
  roleDiffers,
  trackRoleChoice,
  trackRolePlan,
} from "../bus-role.js";

const project = {
  buses: [
    { id: "m", name: "Music", kind: "music" },
    { id: "v", name: "Voices", kind: null },
    { id: "e", name: "Empty", kind: "music" },
  ],
  tracks: [
    { id: "a", bus: "m", kind: "music", follow_bus_role: true },
    { id: "b", bus: "m", kind: "speech", follow_bus_role: false },
    { id: "c", bus: "v", kind: "speech" },
    { id: "d", bus: null, kind: "music" },
    { id: "f", bus: "m", kind: "music", follow_bus_role: false },
  ],
};
const state = (extra = {}) => ({ project, selection: new Set(), ...extra });

describe("roleDiffers", () => {
  test("a track whose kind is not its bus's role differs", () => {
    assert.equal(roleDiffers(project, project.tracks[1]), true);
    assert.equal(roleDiffers(project, project.tracks[0]), false);
  });
  test("a following track never differs; an override with the same kind does not either", () => {
    assert.equal(roleDiffers(project, { ...project.tracks[1], follow_bus_role: true }), false);
    assert.equal(roleDiffers(project, project.tracks[4]), false);
  });
  test("a bus without a role, or no bus, never flags", () => {
    assert.equal(roleDiffers(project, project.tracks[2]), false);
    assert.equal(roleDiffers(project, project.tracks[3]), false);
  });
});

describe("busRoleStatus", () => {
  test("counts the tracks that differ", () => {
    assert.deepEqual(busRoleStatus(project, "m"), { role: "music", total: 3, differ: 1 });
  });
  test("no role: nothing differs; empty bus: zero of zero", () => {
    assert.deepEqual(busRoleStatus(project, "v"), { role: null, total: 1, differ: 0 });
    assert.deepEqual(busRoleStatus(project, "e"), { role: "music", total: 0, differ: 0 });
  });
  test("all match: none differ", () => {
    const p = { ...project, tracks: [project.tracks[0]] };
    assert.equal(busRoleStatus(p, "m").differ, 0);
  });
});

describe("plans", () => {
  test("set role: one set_bus on the bus in focus", () => {
    const plan = busRolePlan(state({ focusBus: "v" }), "music");
    assert.equal(plan.op, "set_bus");
    assert.deepEqual(plan.args, { bus_id: "v", kind: "music" });
    assert.equal(busRolePlan(state({ focusBus: "m" }), null).args.kind, null);
  });
  test("no bus in focus, or the role already set: null", () => {
    assert.equal(busRolePlan(state(), "music"), null);
    assert.equal(busRolePlan(state({ focusBus: "m" }), "music"), null);
  });
  test("match: the focused track follows its bus's role", () => {
    const plan = matchRolePlan(state({ focusTrack: "b" }));
    assert.equal(plan.op, "set_track");
    assert.deepEqual(plan.args, { track_id: "b", follow_bus_role: true });
    // Same kind but not following: choosing Match still sets the flag.
    assert.deepEqual(matchRolePlan(state({ focusTrack: "f" })).args, {
      track_id: "f",
      follow_bus_role: true,
    });
    assert.equal(matchRolePlan(state({ focusTrack: "a" })), null);
    assert.equal(matchRolePlan(state({ focusTrack: "d" })), null);
    assert.equal(matchRolePlan(state({ focusTrack: "c" })), null);
  });
  test("speech / music: an override of the kind", () => {
    const plan = trackRolePlan(state({ focusTrack: "a" }), "speech");
    assert.deepEqual(plan.args, { track_id: "a", kind: "speech" });
    assert.equal(trackRolePlan(state({ focusTrack: "b" }), "speech"), null);
    assert.deepEqual(trackRolePlan(state({ focusTrack: "a" }), "music").args, {
      track_id: "a",
      kind: "music",
    });
    assert.equal(trackRolePlan(state({ focusTrack: "d" }), "music"), null);
  });
  test("the dropdown's choice", () => {
    assert.equal(trackRoleChoice(project, project.tracks[0]), "match");
    assert.equal(trackRoleChoice(project, project.tracks[1]), "speech");
    assert.equal(trackRoleChoice(project, project.tracks[3]), "music");
  });
  test("reapply: set_bus with the bus's own role, only when a child differs", () => {
    const plan = reapplyRolePlan(state({ focusBus: "m" }));
    assert.equal(plan.op, "set_bus");
    assert.deepEqual(plan.args, { bus_id: "m", kind: "music" });
    assert.equal(reapplyRolePlan(state({ focusBus: "v" })), null);
    assert.equal(reapplyRolePlan(state({ focusBus: "e" })), null);
  });
});
