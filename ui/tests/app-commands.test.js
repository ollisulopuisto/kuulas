import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { registerAppCommands, seekOffsets, stepTrack } from "../app-commands.js";
import { createRegistry } from "../commands.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";

const project = { rate: 48000, tracks: [{ id: "a" }, { id: "b" }, { id: "c" }] };

describe("track stepping", () => {
  test("moves to the next or previous track and stops at the ends", () => {
    assert.equal(stepTrack(project, "a", 1), "b");
    assert.equal(stepTrack(project, "b", -1), "a");
    assert.equal(stepTrack(project, "a", -1), "a");
    assert.equal(stepTrack(project, "c", 1), "c");
  });
  test("with no focus Down picks the first and Up the last; no project, nothing", () => {
    assert.equal(stepTrack(project, null, 1), "a");
    assert.equal(stepTrack(project, null, -1), "c");
    assert.equal(stepTrack(null, null, 1), null);
    assert.equal(stepTrack({ tracks: [] }, null, 1), null);
  });
});

describe("seek offsets", () => {
  test("1 s, 5 s and 10 ms in frames", () => {
    assert.deepEqual(seekOffsets(48000), { near: 48000, far: 240000, fine: 480 });
  });
});

describe("the commands the app registers", () => {
  function setup(state = {}) {
    const calls = [];
    const registry = createRegistry();
    const actions = new Proxy(
      {},
      {
        get:
          (_t, name) =>
          (...a) =>
            calls.push([name, ...a]),
      },
    );
    const app = {
      undo: () => calls.push(["undo"]),
      redo: () => calls.push(["redo"]),
      chooseMedia: () => calls.push(["import"]),
      focusName: () => calls.push(["rename"]),
      seek: (frame) => calls.push(["seek", frame]),
      totalFrames: () => 480000,
      patch: (p) => calls.push(["patch", p]),
      getState: () => state,
      openPalette: () => calls.push(["palette"]),
      openKeys: () => calls.push(["keys"]),
      importKeys: () => calls.push(["importKeys"]),
      exportKeys: () => calls.push(["exportKeys"]),
      resetKeys: () => calls.push(["resetKeys"]),
    };
    registerAppCommands(registry, { actions, app });
    return { registry, calls };
  }

  test("every registered id is in the keymap data", () => {
    const { registry } = setup();
    const ids = new Set(DEFAULT_KEYMAP.map((e) => e.id));
    for (const id of registry.ids()) assert.ok(ids.has(id), id);
  });

  test("undo and redo can only apply when there is something to undo or redo", () => {
    const { registry } = setup();
    assert.equal(registry.can("edit.undo", { canUndo: false }), false);
    assert.equal(registry.can("edit.undo", { canUndo: true }), true);
    assert.equal(registry.can("edit.redo", { canRedo: false }), false);
  });

  test("the playhead commands need a project and move by the right amount", () => {
    const state = { project, playhead: 100000 };
    const { registry, calls } = setup(state);
    assert.equal(registry.can("nav.start", {}), false);
    assert.equal(registry.can("nav.start", state), true);
    registry.run("nav.start");
    registry.run("nav.end");
    registry.run("nav.forward");
    registry.run("nav.back_far");
    registry.run("nav.back_fine");
    assert.deepEqual(calls, [
      ["seek", 0],
      ["seek", 480000],
      ["seek", 148000],
      ["seek", 0],
      ["seek", 99520],
    ]);
  });

  test("seeking never goes before zero or past the end", () => {
    const { registry, calls } = setup({ project, playhead: 10 });
    registry.run("nav.back");
    assert.deepEqual(calls, [["seek", 0]]);
  });

  test("track.next focuses the next track and clears a focused bus", () => {
    const { registry, calls } = setup({ project, focusTrack: "a" });
    registry.run("track.next");
    assert.deepEqual(calls, [["patch", { focusTrack: "b", focusBus: null }]]);
  });

  test("mark.in and mark.out set the points at the playhead", () => {
    const { registry, calls } = setup({ project, playhead: 5 });
    registry.run("mark.in");
    registry.run("mark.out");
    assert.deepEqual(calls, [
      ["patch", { inPoint: 5 }],
      ["patch", { outPoint: 5 }],
    ]);
  });

  test("rename needs a focused track or bus", () => {
    const { registry } = setup();
    assert.equal(registry.can("rename", { focusTrack: null, focusBus: null }), false);
    assert.equal(registry.can("rename", { focusTrack: "a" }), true);
  });

  test("hints are given for the commands that have a one-line description", () => {
    const { registry } = setup();
    assert.equal(registry.hintKey("edit.undo"), "cmd.edit.undo.hint");
  });
});
