import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { initialState, reduceLive, serverPatch } from "../store.js";

describe("client state", () => {
  test("holds the fields the plan lists, with selection a Set", () => {
    const s = initialState();
    for (const key of [
      "project",
      "head",
      "canUndo",
      "canRedo",
      "words",
      "selection",
      "focusTrack",
      "playhead",
      "inPoint",
      "outPoint",
      "zoom",
      "scroll",
      "playing",
    ]) {
      assert.ok(key in s, key);
    }
    assert.ok(s.selection instanceof Set);
  });

  test("a server answer maps to the client's names", () => {
    const patch = serverPatch({
      project: { tracks: [] },
      head: "h1",
      can_undo: true,
      can_redo: false,
      missing: [],
    });
    assert.deepEqual(patch, { project: { tracks: [] }, head: "h1", canUndo: true, canRedo: false });
  });

  test("a selection of clips that no longer exist is dropped", () => {
    const state = { ...initialState(), selection: new Set(["gone", "c1"]) };
    const patch = serverPatch(
      { project: { tracks: [{ id: "t", clips: [{ id: "c1" }] }] }, head: "h" },
      state,
    );
    assert.deepEqual([...patch.selection], ["c1"]);
  });
});

describe("the placeholder selection (WP43)", () => {
  const answer = (placeholders) => ({
    project: { tracks: [], ...(placeholders ? { placeholders } : {}) },
    head: "h",
  });

  test("starts empty", () => {
    assert.equal(initialState().placeholderSelected, null);
  });

  test("a placeholder that no longer exists is dropped from the selection", () => {
    const state = { ...initialState(), placeholderSelected: "h1" };
    assert.equal(serverPatch(answer(undefined), state).placeholderSelected, null);
    assert.equal(serverPatch(answer([{ id: "h2" }]), state).placeholderSelected, null);
  });

  test("one that is still there stays", () => {
    const state = { ...initialState(), placeholderSelected: "h1" };
    assert.equal("placeholderSelected" in serverPatch(answer([{ id: "h1" }]), state), false);
  });
});

describe("live messages", () => {
  const state = { ...initialState(), head: "h1" };

  test("a position that says playback ended puts the shuttle back to 1x", () => {
    const out = reduceLive(state, { type: "position", position: 0, playing: false });
    assert.deepEqual(out.patch, { playhead: 0, playing: false, speed: 1 });
  });

  test("position moves the playhead and the playing flag", () => {
    const out = reduceLive(state, { type: "position", position: 4800, playing: true });
    assert.deepEqual(out.patch, { playhead: 4800, playing: true });
    assert.equal(out.refresh, false);
  });

  test("a stopped message leaves the playhead where the engine stopped", () => {
    const out = reduceLive(
      { ...state, playing: true },
      { type: "position", position: 9, playing: false },
    );
    assert.deepEqual(out.patch, { playhead: 9, playing: false, speed: 1 });
  });

  test("a changed head, from state_changed or hello, asks for a refresh", () => {
    assert.equal(reduceLive(state, { type: "state_changed", head: "h2" }).refresh, true);
    assert.equal(reduceLive(state, { type: "hello", head: "h2" }).refresh, true);
    assert.equal(reduceLive(state, { type: "state_changed", head: "h1" }).refresh, false);
    assert.equal(reduceLive(state, { type: "hello", head: "h1" }).refresh, false);
  });

  test("a notice is shown with the server's own text", () => {
    const out = reduceLive(state, { type: "notice", id: 3, text: "Device lost" });
    assert.deepEqual(out.notice, { id: 3, text: "Device lost" });
  });

  test("jobs and unknown messages change nothing", () => {
    assert.deepEqual(reduceLive(state, { type: "jobs", jobs: [] }).patch, {});
    assert.deepEqual(reduceLive(state, { type: "whatever" }).patch, {});
  });
});

describe("editing defaults", () => {
  test("group editing is on at the start and the nudge step is 10 ms", () => {
    assert.equal(initialState().groupEditing, true);
    assert.equal(initialState().nudgeMs, 10);
  });
});
