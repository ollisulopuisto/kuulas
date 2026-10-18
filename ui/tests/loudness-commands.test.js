import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import {
  DEFAULT_LOUDNESS_LUFS,
  matchTargets,
  registerLoudnessCommands,
  reportToast,
} from "../loudness-commands.js";

const clip = (id) => ({ id, start: 0, length: 100 });
const project = {
  rate: 100,
  tracks: [
    { id: "A", clips: [clip("a1"), clip("a2")] },
    { id: "B", clips: [clip("b1")] },
  ],
};
const state = (extra = {}) => ({ project, selection: new Set(), focusTrack: "A", ...extra });

describe("which clips are matched", () => {
  test("the selected clips", () => {
    assert.deepEqual(matchTargets(state({ selection: new Set(["b1", "a1"]) })), ["a1", "b1"]);
  });
  test("with none selected, every clip of the current track", () => {
    assert.deepEqual(matchTargets(state()), ["a1", "a2"]);
  });
  test("no selection and no current track: nothing", () => {
    assert.deepEqual(matchTargets(state({ focusTrack: null })), []);
    assert.deepEqual(matchTargets({ project: null }), []);
  });
});

describe("the toast text", () => {
  const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;
  test("matched and skipped counts", () => {
    const text = reportToast({ matched: [{}, {}], skipped: ["x"] }, t);
    assert.match(text, /^ui\.loudness\.done/);
    assert.match(text, /"count":2/);
    assert.match(text, /"skipped":1/);
  });
});

function setup(current, report = { matched: [{}], skipped: [] }) {
  const registry = createRegistry();
  const calls = { match: [], toasts: [] };
  registerLoudnessCommands(registry, {
    t: (key, values = {}) => `${key}${JSON.stringify(values)}`,
    app: {
      getState: () => current,
      toast: (text, options) => calls.toasts.push([text, options]),
      matchLoudness: async (ids, target) => {
        calls.match.push([ids, target]);
        return report;
      },
    },
  });
  return { registry, calls };
}

describe("clip.match_loudness", () => {
  test("is registered, has no default key, and is disabled without clips", () => {
    const { registry } = setup(state());
    assert.equal(registry.status("clip.match_loudness"), "ready");
    assert.equal(registry.can("clip.match_loudness", state()), true);
    assert.equal(registry.can("clip.match_loudness", state({ focusTrack: null })), false);
  });

  test("measures at -16 LUFS: a Measuring toast first, then the report with Undo", async () => {
    const current = state();
    const { registry, calls } = setup(current, { matched: [{}, {}], skipped: ["a2"] });
    registry.run("clip.match_loudness", null, current);
    assert.match(calls.toasts[0][0], /^ui\.loudness\.measuring/);
    assert.deepEqual(calls.toasts[0][1], { undo: false });
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(calls.match, [[["a1", "a2"], DEFAULT_LOUDNESS_LUFS]]);
    assert.equal(DEFAULT_LOUDNESS_LUFS, -16);
    assert.match(calls.toasts[1][0], /^ui\.loudness\.done/);
    assert.deepEqual(calls.toasts[1][1], { undo: true });
  });

  test("nothing matched (all silent) offers no Undo", async () => {
    const current = state();
    const { registry, calls } = setup(current, { matched: [], skipped: ["a1", "a2"] });
    registry.run("clip.match_loudness", null, current);
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(calls.toasts[1][1], { undo: false });
  });

  test("a second run while measuring is ignored", async () => {
    const current = state();
    const { registry, calls } = setup(current);
    registry.run("clip.match_loudness", null, current);
    registry.run("clip.match_loudness", null, current);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(calls.match.length, 1);
  });
});
