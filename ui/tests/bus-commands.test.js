import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { registerAppCommands } from "../app-commands.js";
import { createRegistry } from "../commands.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { autoFitKey, fitHeight } from "../lane-sizing.js";
import { MENU, menuTargets } from "../menu-model.js";

const project = {
  rate: 48000,
  buses: [{ id: "v", name: "Voices" }],
  tracks: [
    { id: "a", bus: "v", clips: [] },
    { id: "b", bus: "v", clips: [] },
  ],
};

function setup(initial) {
  let state = { project, collapsedBuses: new Set(), ...initial };
  const registry = createRegistry();
  registerAppCommands(registry, {
    actions: {},
    app: {
      getState: () => state,
      patch: (patch) => {
        state = { ...state, ...patch };
      },
    },
  });
  return { registry, get: () => state };
}

describe("bus.collapse and bus.expand", () => {
  test("they are ready, with keys in the sheet", () => {
    const { registry } = setup({});
    for (const id of ["bus.collapse", "bus.expand"]) {
      assert.equal(registry.status(id), "ready");
      assert.ok(DEFAULT_KEYMAP.some((entry) => entry.id === id));
    }
  });
  test("collapse acts on the bus of the focused track and moves the focus to the bus", () => {
    const { registry, get } = setup({ focusTrack: "a" });
    assert.equal(registry.can("bus.collapse", get()), true);
    assert.equal(registry.can("bus.expand", get()), false);
    registry.run("bus.collapse", null, get());
    assert.deepEqual([...get().collapsedBuses], ["v"]);
    assert.equal(get().focusBus, "v");
    assert.equal(get().focusTrack, null);
    assert.equal(registry.can("bus.collapse", get()), false);
    registry.run("bus.expand", null, get());
    assert.equal(get().collapsedBuses.size, 0);
  });
  test("with nothing in focus neither is enabled", () => {
    const { registry, get } = setup({});
    assert.equal(registry.can("bus.collapse", get()), false);
    assert.equal(registry.can("bus.expand", get()), false);
  });
  test("collapse all and expand all", () => {
    const { registry, get } = setup({});
    assert.equal(registry.can("view.expand_all_buses", get()), false);
    registry.run("view.collapse_all_buses", null, get());
    assert.deepEqual([...get().collapsedBuses], ["v"]);
    assert.equal(registry.can("view.collapse_all_buses", get()), false);
    registry.run("view.expand_all_buses", null, get());
    assert.equal(get().collapsedBuses.size, 0);
  });
  test("both are in the View menu", () => {
    const view = MENU.find((menu) => menu.id === "view");
    const ids = menuTargets([view]);
    assert.ok(ids.includes("view.collapse_all_buses"));
    assert.ok(ids.includes("view.expand_all_buses"));
  });
});

describe("fitting tracks with collapsed buses", () => {
  const input = { project, available: 400, busHeight: 32, groupGap: 14 };
  test("a collapsed bus has no member lanes, so the rest get more room", () => {
    const open = fitHeight(input);
    const shut = fitHeight({ ...input, collapsed: new Set(["v"]) });
    assert.equal(shut, null, "nothing left to fit");
    assert.ok(open > 0);
  });
  test("collapsing changes the auto-fit key", () => {
    assert.notEqual(autoFitKey(input), autoFitKey({ ...input, collapsed: new Set(["v"]) }));
  });
});
