import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { HINTS, noteUse } from "../use-hints.js";

const empty = { counts: {}, shown: [] };
const times = (state, id, n) => {
  let hint = null;
  let at = state;
  for (let i = 0; i < n; i += 1) {
    const step = noteUse(at, id);
    at = step.state;
    hint = step.hint ?? hint;
  }
  return { state: at, hint };
};

describe("use hints", () => {
  test("ten hand mutes suggest Auto-Silence, not nine", () => {
    assert.equal(times(empty, "clip.mute", 9).hint, null);
    assert.equal(times(empty, "clip.mute", 10).hint, "ui.hint.use.auto_silence");
  });

  test("quick mutes count with mutes", () => {
    const a = times(empty, "clip.mute", 5);
    assert.equal(times(a.state, "clip.quick_mute", 5).hint, "ui.hint.use.auto_silence");
  });

  test("a hint is shown once, however long the user keeps muting", () => {
    const first = times(empty, "clip.mute", 10);
    assert.equal(times(first.state, "clip.mute", 30).hint, null);
  });

  test("a user who already ran Auto-Silence is never told about it", () => {
    const used = noteUse(empty, "app.auto_silence").state;
    assert.equal(times(used, "clip.mute", 50).hint, null);
  });

  test("other commands change nothing", () => {
    const step = noteUse(empty, "edit.undo");
    assert.equal(step.hint, null);
    assert.deepEqual(step.state, empty);
  });

  test("the input is never changed, and the hint names no button and no position", () => {
    const frozen = Object.freeze({ counts: Object.freeze({}), shown: Object.freeze([]) });
    assert.doesNotThrow(() => noteUse(frozen, "clip.mute"));
    for (const hint of HINTS)
      assert.deepEqual(Object.keys(hint).sort(), ["after", "commands", "id", "key", "stop"]);
  });
});

describe("remembering the counter", () => {
  const store = (initial) => {
    const data = new Map(initial ? [["use.hints", initial]] : []);
    return {
      getJson: (key, fallback) => (data.has(key) ? JSON.parse(data.get(key)) : fallback),
      setJson: (key, value) => data.set(key, JSON.stringify(value)),
    };
  };

  test("round trip", async () => {
    const { readUse, writeUse } = await import("../use-hints.js");
    const prefs = store();
    writeUse(prefs, { counts: { auto_silence: 4 }, shown: ["x"] });
    assert.deepEqual(readUse(prefs), { counts: { auto_silence: 4 }, shown: ["x"] });
  });

  test("bad data falls back to an empty counter", async () => {
    const { readUse } = await import("../use-hints.js");
    for (const bad of ['"text"', "[1]", '{"counts":5,"shown":"no"}', "null"])
      assert.deepEqual(readUse(store(bad)), { counts: {}, shown: [] }, bad);
  });
});
