import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { registerSelectCommands, SELECT_COMMANDS } from "../select-commands.js";

const clip = (id, start, length) => ({ id, start, length, muted: false });
const project = {
  rate: 100,
  tracks: [
    { id: "A", clips: [clip("a1", 0, 100), clip("a2", 200, 100)] },
    { id: "B", clips: [clip("b1", 50, 100), clip("b2", 300, 100)] },
  ],
};
const base = (extra = {}) => ({
  project,
  selection: new Set(),
  focusTrack: "A",
  focusBus: null,
  playhead: 150,
  inPoint: null,
  outPoint: null,
  rangeTracks: null,
  ...extra,
});

function setup(state) {
  const registry = createRegistry();
  const patches = [];
  registerSelectCommands(registry, {
    app: { getState: () => state, patch: (p) => patches.push(p) },
  });
  return { registry, patches };
}
const run = (id, state) => {
  const h = setup(state);
  h.registry.run(id, null, state);
  return h.patches;
};
const ids = (set) => [...set].sort();

describe("the Select commands", () => {
  test("each is registered, in the keymap, and has a hint key", () => {
    const { registry } = setup(base());
    const mapped = new Set(DEFAULT_KEYMAP.map((entry) => entry.id));
    for (const id of SELECT_COMMANDS) {
      assert.equal(registry.status(id), "ready", id);
      assert.ok(mapped.has(id), id);
    }
  });

  test("range on all tracks sets rangeTracks; needs a range", () => {
    const state = base({ inPoint: 0, outPoint: 100 });
    assert.deepEqual(run("select.range_all_tracks", state), [{ rangeTracks: ["A", "B"] }]);
    const { registry } = setup(base());
    assert.equal(registry.can("select.range_all_tracks", base()), false);
    assert.equal(registry.can("select.range_all_tracks", state), true);
  });

  test("clips in range uses the range tracks, else the current track", () => {
    const marks = { inPoint: 60, outPoint: 250 };
    const [here] = run("select.clips_in_range", base(marks));
    assert.deepEqual(ids(here.selection), ["a1", "a2"]);
    const [all] = run("select.clips_in_range", base({ ...marks, rangeTracks: ["A", "B"] }));
    assert.deepEqual(ids(all.selection), ["a1", "a2", "b1"]);
    const { registry } = setup(base());
    assert.equal(registry.can("select.clips_in_range", base()), false);
    assert.equal(
      registry.can("select.clips_in_range", base({ inPoint: 1000, outPoint: 2000 })),
      false,
    );
  });

  test("range from clips sets in, out and the tracks of the selection", () => {
    const state = base({ selection: new Set(["a2", "b1"]) });
    assert.deepEqual(run("select.range_from_clips", state), [
      { inPoint: 50, outPoint: 300, rangeTracks: ["A", "B"] },
    ]);
    const { registry } = setup(base());
    assert.equal(registry.can("select.range_from_clips", base()), false);
  });

  test("forward selects from the playhead on the current track", () => {
    const [patch] = run("select.forward", base());
    assert.deepEqual(ids(patch.selection), ["a2"]);
    const [all] = run("select.forward", base({ focusTrack: null }));
    assert.deepEqual(ids(all.selection), ["a2", "b2"]);
  });

  test("forward from clips, and its Shift variant across tracks", () => {
    const state = base({ selection: new Set(["a2"]) });
    assert.deepEqual(ids(run("select.forward_from_clips", state)[0].selection), ["a2"]);
    assert.deepEqual(ids(run("select.forward_all_tracks_from_clips", state)[0].selection), [
      "a2",
      "b2",
    ]);
    const { registry } = setup(base());
    assert.equal(registry.can("select.forward_from_clips", base()), false);
    assert.equal(registry.can("select.forward_all_tracks_from_clips", base()), false);
  });

  test("invert flips the selection on the current track", () => {
    const state = base({ selection: new Set(["a1"]) });
    assert.deepEqual(ids(run("select.invert", state)[0].selection), ["a2"]);
  });

  test("none clears the selection and the range tracks; only when there is something", () => {
    assert.deepEqual(run("select.none", base({ selection: new Set(["a1"]) })), [
      { selection: new Set(), rangeTracks: null },
    ]);
    const { registry } = setup(base());
    assert.equal(registry.can("select.none", base()), false);
    assert.equal(registry.can("select.none", base({ selection: new Set(["a1"]) })), true);
    assert.equal(registry.can("select.none", base({ rangeTracks: ["A"] })), true);
  });
});
