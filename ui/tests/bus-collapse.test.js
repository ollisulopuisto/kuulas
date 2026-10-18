import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  busOfFocus,
  collapseAllChange,
  collapseChange,
  collapsibleBuses,
  memberClipsAt,
  toggleChange,
} from "../bus-collapse.js";

const project = {
  buses: [
    { id: "v", name: "Voices" },
    { id: "m", name: "Music" },
    { id: "w", name: "Two" },
  ],
  tracks: [
    { id: "a", bus: "v", clips: [{ id: "c1", start: 0, length: 100 }] },
    { id: "b", bus: "v", clips: [{ id: "c2", start: 50, length: 100 }] },
    { id: "mu", bus: "m", clips: [] },
    { id: "x", bus: null, clips: [{ id: "c3", start: 0, length: 500 }] },
    { id: "w1", bus: "w", clips: [] },
    { id: "w2", bus: "w", clips: [] },
  ],
};
const state = (extra = {}) => ({ project, collapsedBuses: new Set(), ...extra });
const list = (set) => (set ? [...set] : set);

describe("which bus a command acts on", () => {
  test("the focused bus, else the bus of the focused track, else none", () => {
    assert.equal(busOfFocus(state({ focusBus: "w" })), "w");
    assert.equal(busOfFocus(state({ focusTrack: "b" })), "v");
    assert.equal(busOfFocus(state({ focusTrack: "x" })), null);
    assert.equal(busOfFocus(state()), null);
    assert.equal(busOfFocus({ project: null }), null);
  });
});

describe("collapsible buses", () => {
  test("only buses with two or more tracks have a row to collapse", () => {
    assert.deepEqual(collapsibleBuses(project), ["v", "w"]);
    assert.deepEqual(collapsibleBuses(null), []);
  });
});

describe("collapse and expand commands", () => {
  test("collapse adds the focused bus; null when nothing would change", () => {
    assert.deepEqual(list(collapseChange(state({ focusTrack: "a" }), true)), ["v"]);
    const shut = state({ focusBus: "v", collapsedBuses: new Set(["v"]) });
    assert.equal(collapseChange(shut, true), null);
    assert.equal(collapseChange(state({ focusTrack: "x" }), true), null);
    assert.equal(collapseChange(state({ focusBus: "m" }), true), null, "merged: no row");
    assert.equal(collapseChange(state(), true), null);
  });
  test("expand removes it; null when already expanded", () => {
    const open = collapseChange(
      state({ focusBus: "v", collapsedBuses: new Set(["v", "w"]) }),
      false,
    );
    assert.deepEqual(list(open), ["w"]);
    assert.equal(collapseChange(state({ focusBus: "v" }), false), null);
  });
  test("a new set every time: the old one is never mutated", () => {
    const before = new Set();
    const next = collapseChange(state({ focusBus: "v", collapsedBuses: before }), true);
    assert.notEqual(next, before);
    assert.equal(before.size, 0);
  });
  test("collapse all and expand all", () => {
    assert.deepEqual(list(collapseAllChange(state(), true)), ["v", "w"]);
    assert.equal(collapseAllChange(state({ collapsedBuses: new Set(["v", "w"]) }), true), null);
    assert.deepEqual(list(collapseAllChange(state({ collapsedBuses: new Set(["v"]) }), true)), [
      "v",
      "w",
    ]);
    assert.equal(collapseAllChange(state(), false), null);
    assert.deepEqual(
      list(collapseAllChange(state({ collapsedBuses: new Set(["v", "gone"]) }), false)),
      [],
    );
  });
  test("toggle flips one bus", () => {
    assert.deepEqual(list(toggleChange(state(), "v")), ["v"]);
    assert.deepEqual(list(toggleChange(state({ collapsedBuses: new Set(["v"]) }), "v")), []);
  });
});

describe("Shift+click on a collapsed bus", () => {
  test("the member clips that hold the frame", () => {
    assert.deepEqual(memberClipsAt(project, "v", 75), ["c1", "c2"]);
    assert.deepEqual(memberClipsAt(project, "v", 120), ["c2"]);
    assert.deepEqual(memberClipsAt(project, "v", 400), []);
    assert.deepEqual(memberClipsAt(project, "nope", 10), []);
  });
});
