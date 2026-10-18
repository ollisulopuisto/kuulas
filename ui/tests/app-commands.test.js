import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { prerollStart, registerAppCommands, seekOffsets, stepTrack } from "../app-commands.js";
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

describe("play from a few seconds before the playhead", () => {
  test("starts 3 s back by default and never before the start", () => {
    assert.equal(prerollStart(480000, 48000), 336000);
    assert.equal(prerollStart(100000, 48000), 0);
    assert.equal(prerollStart(0, 48000), 0);
  });
  test("the length can be given", () => {
    assert.equal(prerollStart(480000, 48000, 5), 240000);
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
      openHelp: () => calls.push(["help"]),
      importKeys: () => calls.push(["importKeys"]),
      exportKeys: () => calls.push(["exportKeys"]),
      resetKeys: () => calls.push(["resetKeys"]),
      restoreStep: () => calls.push(["restoreStep"]),
      openHistory: () => calls.push(["openHistory"]),
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

  test("history.restore runs in the History panel on a pick that is not the head", () => {
    const { registry, calls } = setup();
    const state = { panel: "history", head: "b", historySelected: "a" };
    assert.equal(registry.can("history.restore", { ...state, panel: "timeline" }), false);
    assert.equal(registry.can("history.restore", { ...state, historySelected: "b" }), false);
    assert.equal(registry.run("history.restore", null, state), true);
    assert.equal(registry.run("history.open", null, {}), true);
    assert.deepEqual(calls, [["restoreStep"], ["openHistory"]]);
  });

  test("clearing the in and out points", () => {
    const { registry, calls } = setup({ project });
    assert.equal(registry.run("mark.clear_in", null, { project }), true);
    assert.equal(registry.run("mark.clear_out", null, { project }), true);
    assert.equal(registry.run("mark.clear", null, { project }), true);
    assert.deepEqual(calls, [
      ["patch", { inPoint: null, rangeTracks: new Set() }],
      ["patch", { outPoint: null, rangeTracks: new Set() }],
      ["patch", { inPoint: null, outPoint: null, rangeTracks: new Set() }],
    ]);
    assert.equal(registry.can("mark.clear", {}), false);
  });

  test("0 shows the whole edit and F fits the selection", () => {
    const { registry, calls } = setup({ project });
    registry.run("view.fit", null, { project });
    registry.run("view.fit_selection", null, { project });
    assert.deepEqual(calls, [["fitView"], ["fitSelection"]]);
  });

  test("the four pause-break choices call setPauseBreak and need no project", () => {
    const { registry, calls } = setup({});
    for (const id of ["1_5", "3", "6", "never"]) {
      assert.equal(registry.run(`view.pause_${id}`, null, {}), true);
    }
    assert.deepEqual(calls, [
      ["setPauseBreak", "1_5"],
      ["setPauseBreak", "3"],
      ["setPauseBreak", "6"],
      ["setPauseBreak", "never"],
    ]);
  });

  test("fit tracks and auto-fit need a project and call the actions", () => {
    const { registry, calls } = setup({ project });
    assert.equal(registry.can("view.fit_tracks", {}), false);
    assert.equal(registry.can("view.auto_fit_tracks", {}), false);
    registry.run("view.fit_tracks", null, { project });
    registry.run("view.auto_fit_tracks", null, { project });
    assert.deepEqual(calls, [["fitTracks"], ["toggleAutoFitTracks"]]);
  });

  test("P plays from the pre-roll before the playhead and needs a project", () => {
    const { registry, calls } = setup({ project, playhead: 480000 });
    assert.equal(registry.can("transport.play_before", { project }), true);
    assert.equal(registry.can("transport.play_before", {}), false);
    assert.equal(registry.run("transport.play_before", null, { project, playhead: 480000 }), true);
    assert.deepEqual(calls, [["playFrom", 336000]]);
  });

  test("the loop toggle needs a range to loop, or the loop already on", () => {
    const { registry, calls } = setup({ project });
    const idle = { project, loop: false, inPoint: null, outPoint: null, selection: new Set() };
    assert.equal(registry.can("transport.loop", idle), false);
    assert.equal(registry.can("transport.loop", { ...idle, inPoint: 10, outPoint: 90 }), true);
    assert.equal(registry.can("transport.loop", { ...idle, loop: true }), true);
    assert.equal(registry.can("transport.loop", {}), false);
    registry.run("transport.loop", null, { ...idle, inPoint: 10, outPoint: 90 });
    assert.deepEqual(calls, [["toggleLoop"]]);
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

  test("the shuttle commands press J, K and L and need a project", () => {
    const state = { project };
    const { registry, calls } = setup(state);
    assert.equal(registry.can("transport.shuttle_forward", {}), false);
    assert.equal(registry.can("transport.shuttle_forward", state), true);
    registry.run("transport.shuttle_back", null, state);
    registry.run("transport.shuttle_stop", null, state);
    registry.run("transport.shuttle_forward", null, state);
    assert.deepEqual(calls, [
      ["shuttle", "j"],
      ["shuttle", "k"],
      ["shuttle", "l"],
    ]);
  });

  test("the fast-listening key says it is not built yet", () => {
    const { registry, calls } = setup({ project });
    assert.equal(registry.status("transport.speed"), "ready");
    registry.run("transport.speed", null, { project });
    assert.deepEqual(calls, [["fastListening"]]);
  });

  test("mark.in and mark.out set the points at the playhead", () => {
    const { registry, calls } = setup({ project, playhead: 5 });
    registry.run("mark.in");
    registry.run("mark.out");
    assert.deepEqual(calls, [
      ["patch", { inPoint: 5, rangeTracks: new Set() }],
      ["patch", { outPoint: 5, rangeTracks: new Set() }],
    ]);
  });

  test("rename needs a focused track or bus", () => {
    const { registry } = setup();
    assert.equal(registry.can("rename", { focusTrack: null, focusBus: null }), false);
    assert.equal(registry.can("rename", { focusTrack: "a" }), true);
  });

  test("help.open is always available and opens help", () => {
    const { registry, calls } = setup();
    assert.equal(registry.can("help.open", undefined), true);
    assert.equal(registry.can("help.open", {}), true);
    assert.equal(registry.hintKey("help.open"), "cmd.help.open.hint");
    registry.run("help.open", null, {});
    assert.deepEqual(calls, [["help"]]);
  });

  test("hints are given for the commands that have a one-line description", () => {
    const { registry } = setup();
    assert.equal(registry.hintKey("edit.undo"), "cmd.edit.undo.hint");
  });
});
