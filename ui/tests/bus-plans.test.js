import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { busMutePlan, removeFromBusPlan, ungroupPlan } from "../edit-plans.js";

const project = {
  buses: [
    { id: "v", name: "Voices", mute: false },
    { id: "m", name: "Music", mute: true },
  ],
  tracks: [
    { id: "a", bus: "v", clips: [] },
    { id: "b", bus: "m", clips: [] },
    { id: "x", bus: null, clips: [] },
  ],
};
const state = (extra = {}) => ({ project, selection: new Set(), ...extra });

describe("bus mute", () => {
  test("toggles the focused bus, or the bus of the focused track", () => {
    assert.deepEqual(busMutePlan(state({ focusBus: "v" })).args, { bus_id: "v", mute: true });
    assert.deepEqual(busMutePlan(state({ focusBus: "m" })).args, { bus_id: "m", mute: false });
    assert.deepEqual(busMutePlan(state({ focusTrack: "a" })).args, { bus_id: "v", mute: true });
    assert.equal(busMutePlan(state({ focusBus: "v" })).op, "set_bus");
  });
  test("nothing to act on: null", () => {
    assert.equal(busMutePlan(state({ focusTrack: "x" })), null);
    assert.equal(busMutePlan(state()), null);
  });
});

describe("ungroup", () => {
  test("deletes the bus: one edit puts every member on no bus", () => {
    const plan = ungroupPlan(state({ focusBus: "v" }));
    assert.equal(plan.op, "delete_bus");
    assert.deepEqual(plan.args, { bus_id: "v" });
    assert.equal(plan.label.key, "ui.edit.label.ungroup");
    assert.equal(ungroupPlan(state({ focusTrack: "b" })).args.bus_id, "m");
  });
  test("no bus in focus: null", () => {
    assert.equal(ungroupPlan(state({ focusTrack: "x" })), null);
  });
});

describe("remove from bus", () => {
  test("moves the current track to no bus", () => {
    const plan = removeFromBusPlan(state({ focusTrack: "a" }));
    assert.equal(plan.op, "set_track");
    assert.deepEqual(plan.args, { track_id: "a", bus: null });
  });
  test("a track on no bus, or a bus in focus: null", () => {
    assert.equal(removeFromBusPlan(state({ focusTrack: "x" })), null);
    assert.equal(removeFromBusPlan(state({ focusBus: "v" })), null);
  });
});
