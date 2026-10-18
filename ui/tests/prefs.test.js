import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createPrefs } from "../prefs.js";

const memoryStorage = () => {
  const data = new Map();
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
    data,
  };
};
const broken = {
  getItem() {
    throw new Error("blocked");
  },
  setItem() {
    throw new Error("blocked");
  },
  removeItem() {
    throw new Error("blocked");
  },
};

describe("prefs", () => {
  test("round-trips under the kuulas. prefix", () => {
    const storage = memoryStorage();
    const prefs = createPrefs(storage);
    assert.equal(prefs.set("theme", "dark"), true);
    assert.equal(prefs.get("theme"), "dark");
    assert.equal(storage.getItem("kuulas.theme"), "dark");
    prefs.remove("theme");
    assert.equal(prefs.get("theme"), null);
  });
  test("json values", () => {
    const prefs = createPrefs(memoryStorage());
    prefs.setJson("recent", ["a", "b"]);
    assert.deepEqual(prefs.getJson("recent", []), ["a", "b"]);
  });
  test("damaged json gives the fallback", () => {
    const storage = memoryStorage();
    storage.setItem("kuulas.recent", "{nope");
    assert.deepEqual(createPrefs(storage).getJson("recent", ["x"]), ["x"]);
  });
  test("blocked storage never throws", () => {
    const prefs = createPrefs(broken);
    assert.equal(prefs.get("theme"), null);
    assert.equal(prefs.set("theme", "dark"), false);
    assert.equal(prefs.remove("theme"), false);
    assert.deepEqual(prefs.getJson("recent", [1]), [1]);
    assert.equal(prefs.setJson("recent", []), false);
  });
  test("no storage at all works", () => {
    const prefs = createPrefs(null);
    assert.equal(prefs.get("x"), null);
    assert.equal(prefs.set("x", "1"), false);
  });
});
