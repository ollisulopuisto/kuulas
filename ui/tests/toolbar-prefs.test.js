import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createPrefs } from "../prefs.js";
import { DEFAULT_LAYOUT } from "../toolbar-model.js";
import {
  readLayout,
  readMode,
  readVisible,
  writeLayout,
  writeMode,
  writeVisible,
} from "../toolbar-prefs.js";

const memoryStorage = () => {
  const data = new Map();
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: (key) => data.delete(key),
  };
};
const known = new Set(DEFAULT_LAYOUT);

describe("the layout", () => {
  test("nothing stored: the default", () => {
    assert.deepEqual(readLayout(createPrefs(memoryStorage()), known), DEFAULT_LAYOUT);
  });

  test("what the user arranged comes back in that order", () => {
    const prefs = createPrefs(memoryStorage());
    writeLayout(prefs, ["app.export", "edit.undo"]);
    assert.deepEqual(readLayout(prefs, known), ["app.export", "edit.undo"]);
  });

  test("an empty arrangement is kept: the user removed every button", () => {
    const prefs = createPrefs(memoryStorage());
    writeLayout(prefs, []);
    assert.deepEqual(readLayout(prefs, known), []);
  });

  test("damaged storage falls back to the default", () => {
    const storage = memoryStorage();
    storage.setItem("kuulas.toolbar.layout", "{not json");
    assert.deepEqual(readLayout(createPrefs(storage), known), DEFAULT_LAYOUT);
  });

  test("no storage at all: the default, and writing is only 'not remembered'", () => {
    const prefs = createPrefs(null);
    assert.deepEqual(readLayout(prefs, known), DEFAULT_LAYOUT);
    assert.doesNotThrow(() => writeLayout(prefs, ["edit.undo"]));
  });
});

describe("the mode and the visibility", () => {
  test("the default shows icons with text: text is what helps people find things", () => {
    const prefs = createPrefs(memoryStorage());
    assert.equal(readMode(prefs), "labels");
    assert.equal(readVisible(prefs), true);
  });

  test("a choice is remembered", () => {
    const prefs = createPrefs(memoryStorage());
    writeMode(prefs, "icons");
    writeVisible(prefs, false);
    assert.equal(readMode(prefs), "icons");
    assert.equal(readVisible(prefs), false);
  });

  test("a value that is not a mode is the default", () => {
    const storage = memoryStorage();
    storage.setItem("kuulas.toolbar.mode", "huge");
    assert.equal(readMode(createPrefs(storage)), "labels");
  });
});
