// Double-click (or Shift+Enter) toggles a value between its default and the
// last custom value, for quick A/B listening (owner, 2026-10-18).
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createAbStore, resetValue, toggleValue } from "../ab-value.js";

describe("toggleValue", () => {
  test("a custom value goes to the default and is remembered", () => {
    assert.deepEqual(toggleValue(-2.5, 0, null), { value: 0, stored: -2.5, changed: true });
  });

  test("at the default, the remembered value comes back and stays remembered", () => {
    assert.deepEqual(toggleValue(0, 0, -2.5), { value: -2.5, stored: -2.5, changed: true });
  });

  test("at the default with nothing remembered, nothing happens (the UI flashes)", () => {
    assert.deepEqual(toggleValue(0, 0, null), { value: 0, stored: null, changed: false });
  });

  test("values within a tiny tolerance count as the default", () => {
    assert.equal(toggleValue(0.00001, 0, 3).value, 3);
  });

  test("Alt: reset to the default and forget", () => {
    assert.deepEqual(resetValue(-2.5, 0), { value: 0, stored: null, changed: true });
    assert.deepEqual(resetValue(0, 0), { value: 0, stored: null, changed: false });
  });
});

describe("the remembered values (UI state, lost on reload)", () => {
  test("per field key; set, read, forget", () => {
    const store = createAbStore();
    assert.equal(store.get("clip-gain-c1"), null);
    store.set("clip-gain-c1", -2.5);
    assert.equal(store.get("clip-gain-c1"), -2.5);
    store.set("clip-gain-c1", null);
    assert.equal(store.get("clip-gain-c1"), null);
  });

  test("toggle through the store: two toggles come back where they started", () => {
    const store = createAbStore();
    const first = store.toggle("track-pan-t1", 0.3, 0);
    assert.equal(first.value, 0);
    const second = store.toggle("track-pan-t1", first.value, 0);
    assert.equal(second.value, 0.3);
  });
});
