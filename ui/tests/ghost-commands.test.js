import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { registerAppCommands } from "../app-commands.js";
import { createRegistry } from "../commands.js";
import { registerEditCommands } from "../edit-commands.js";

const S = 48000;
const project = {
  rate: S,
  tracks: [{ id: "A", mute: false, clips: [{ id: "a1", start: 0, length: 10 * S, muted: false }] }],
};
const none = { in: null, out: null };

function marksHarness(state) {
  const registry = createRegistry();
  const patches = [];
  const actions = new Proxy({}, { get: () => () => {} });
  registerAppCommands(registry, {
    actions,
    app: {
      getState: () => state,
      patch: (p) => patches.push(p),
      seek: () => {},
      totalFrames: () => 10 * S,
    },
  });
  return { registry, patches };
}

describe("mark.in and mark.out use the ghost of the last cut", () => {
  const base = { project, inPoint: null, outPoint: null, guessedMarks: none };
  test("OUT after a cut puts IN at the splice and remembers it as a guess", () => {
    const state = { ...base, playhead: 500, ghost: { frame: 100 } };
    const { registry, patches } = marksHarness(state);
    registry.run("mark.out");
    assert.deepEqual(patches, [
      { inPoint: 100, outPoint: 500, guessedMarks: { in: 100, out: null }, rangeTracks: new Set() },
    ]);
  });
  test("IN before the splice puts OUT at the splice", () => {
    const state = { ...base, playhead: 50, ghost: { frame: 100 } };
    const { registry, patches } = marksHarness(state);
    registry.run("mark.in");
    assert.deepEqual(patches, [
      { inPoint: 50, outPoint: 100, guessedMarks: { in: null, out: 100 }, rangeTracks: new Set() },
    ]);
  });
  test("Shift+Alt+I (clear marks) forgets the ghost and the guesses", () => {
    const state = { ...base, inPoint: 1, outPoint: 2, ghost: { frame: 100 } };
    const { registry, patches } = marksHarness(state);
    registry.run("mark.clear");
    assert.deepEqual(patches, [
      { inPoint: null, outPoint: null, ghost: null, guessedMarks: none, rangeTracks: new Set() },
    ]);
  });
});

describe("a finished cut remembers its splice as the ghost", () => {
  function editHarness(state) {
    const registry = createRegistry();
    const sent = [];
    const patches = [];
    registerEditCommands(registry, {
      t: (key) => key,
      formatSeconds: String,
      app: {
        getState: () => state,
        patch: (p) => patches.push(p),
        seek: () => {},
        edit: (change) => sent.push(change),
        toast: () => {},
        now: () => 0,
        copy: () => Promise.resolve(true),
        refreshClipboard: () => {},
      },
    });
    return { registry, sent, patches };
  }
  const cutState = () => ({
    project,
    selection: new Set(),
    focusTrack: "A",
    focusBus: null,
    playhead: 9 * S,
    inPoint: 2 * S,
    outPoint: 6 * S,
    rangeMode: "all",
    trackSelection: new Set(),
  });

  for (const id of ["edit.cut", "edit.lift_cut", "edit.remove"]) {
    test(`${id}: not before the edit is done, then at the start of the range`, () => {
      const state = cutState();
      const h = editHarness(state);
      h.registry.run(id, null, state);
      assert.deepEqual(h.patches, []);
      h.sent[0].done({ project, clipboard: { ok: true, entry: "e1" } });
      assert.ok(
        h.patches.some(
          (p) =>
            p.ghost?.frame === 2 * S && p.guessedMarks?.in === null && p.guessedMarks?.out === null,
        ),
        id,
      );
    });
  }

  test("a delete that keeps the range leaves the ghost alone", () => {
    const state = cutState();
    const h = editHarness(state);
    h.registry.run("edit.delete", null, state);
    h.sent[0].done?.({ project });
    assert.deepEqual(h.patches, []);
  });
});
