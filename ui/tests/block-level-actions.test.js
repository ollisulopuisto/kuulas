import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { createBlockLevelActions } from "../block-level-actions.js";

const row = { start: 120, end: 150, track_ids: ["speaker"] };
const setup = (fail = false) => {
  let state = { focusBus: "old-bus", trackSelection: new Set(["old-track"]) };
  const calls = [];
  const actions = createBlockLevelActions({
    api: {
      renderListen: async (on) => {
        calls.push(["source", on]);
        if (fail) throw new Error("source unavailable");
        return { project: {}, render: { listening: false } };
      },
    },
    getState: () => state,
    setState: (patch) => {
      calls.push(["state", patch]);
      state = { ...state, ...patch };
    },
    transport: { preview: async (...args) => calls.push(["preview", ...args]) },
    jumpTo: (at) => calls.push(["jump", at]),
    onError: (error) => calls.push(["error", error.message]),
  });
  return { actions, calls, state: () => state };
};
test("block jump clears bus focus and moves an existing range selection", () => {
  const h = setup();
  h.actions.onJump(row);
  assert.equal(h.state().focusBus, null);
  assert.equal(h.state().focusTrack, "speaker");
  assert.deepEqual([...h.state().trackSelection], ["speaker"]);
  assert.deepEqual(h.calls.at(-1), ["jump", 120]);
});
test("block listen clears rendered audio before preview without invalidating measured project", async () => {
  const h = setup();
  await h.actions.onListen(row);
  assert.deepEqual(h.calls, [
    ["source", false],
    ["state", { render: { listening: false } }],
    ["preview", 120, 150],
  ]);
  assert.equal("project" in h.state(), false);
});
test("failed edit-source switch never plays the rendered mix", async () => {
  const h = setup(true);
  await h.actions.onListen(row);
  assert.deepEqual(h.calls, [
    ["source", false],
    ["error", "source unavailable"],
  ]);
});
test("app wires the tested block actions into the panel", () => {
  const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  assert.match(app, /\.\.\.createBlockLevelActions\(\{/);
});
