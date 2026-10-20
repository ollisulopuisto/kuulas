import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createPrefs, loadPrefs } from "../prefs.js";

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

const settle = () => new Promise((resolve) => setImmediate(resolve));

const fakeServer = (initial = {}) => {
  const calls = [];
  const state = { prefs: { ...initial }, fail: false };
  const fetchFn = async (url, init) => {
    calls.push({ url, init });
    if (state.fail) throw new Error("down");
    if (init?.method === "PUT") {
      const { set, remove } = JSON.parse(init.body);
      Object.assign(state.prefs, set);
      for (const k of remove) delete state.prefs[k];
    }
    return { ok: true, json: async () => ({ prefs: state.prefs }) };
  };
  return { fetchFn, state, calls };
};

const options = (server, storage = memoryStorage()) => {
  const timers = [];
  return {
    fetchFn: server.fetchFn,
    storage,
    schedule: (fn) => timers.push(fn),
    target: {},
    timers,
  };
};

const storageWith = (entries) => {
  const keys = Object.keys(entries);
  return {
    length: keys.length,
    key: (i) => keys[i],
    getItem: (k) => entries[k] ?? null,
    setItem() {},
    removeItem() {},
  };
};

describe("loadPrefs (server-side store)", () => {
  test("reads what the server holds, with the same API", async () => {
    const server = fakeServer({ "kuulas.fast": '{"speed":1.75}', "kuulas.theme": "dark" });
    const prefs = await loadPrefs(options(server));
    assert.equal(prefs.get("theme"), "dark");
    assert.deepEqual(prefs.getJson("fast", null), { speed: 1.75 });
    assert.equal(prefs.get("missing"), null);
    assert.deepEqual(prefs.getJson("missing", [1]), [1]);
  });
  test("writes through once, debounced", async () => {
    const server = fakeServer({ "kuulas.x": "1" });
    const opts = options(server);
    const prefs = await loadPrefs(opts);
    prefs.set("a", "1");
    prefs.setJson("b", { n: 2 });
    prefs.remove("x");
    assert.equal(opts.timers.length, 1);
    assert.equal(server.calls.filter((c) => c.init?.method === "PUT").length, 0);
    opts.timers[0]();
    await settle();
    assert.deepEqual(server.state.prefs, { "kuulas.a": "1", "kuulas.b": '{"n":2}' });
    assert.equal(prefs.get("a"), "1");
  });
  test("flush writes at once (page hide)", async () => {
    const server = fakeServer({ "kuulas.keep": "1" });
    const prefs = await loadPrefs(options(server));
    prefs.set("a", "2");
    prefs.flush();
    await settle();
    assert.equal(server.state.prefs["kuulas.a"], "2");
  });
  test("a failed write is retried with the next one", async () => {
    const server = fakeServer({ "kuulas.keep": "1" });
    const prefs = await loadPrefs(options(server));
    server.state.fail = true;
    prefs.set("a", "2");
    prefs.flush();
    await settle();
    server.state.fail = false;
    prefs.set("b", "3");
    prefs.flush();
    await settle();
    assert.equal(server.state.prefs["kuulas.a"], "2");
    assert.equal(server.state.prefs["kuulas.b"], "3");
  });
  test("a failed server read falls back to browser storage", async () => {
    const server = fakeServer();
    server.state.fail = true;
    const storage = memoryStorage();
    const prefs = await loadPrefs(options(server, storage));
    prefs.set("theme", "dark");
    assert.equal(storage.getItem("kuulas.theme"), "dark");
    assert.equal(prefs.get("theme"), "dark");
  });
  test("imports kuulas.* keys from browser storage when the server is empty", async () => {
    const server = fakeServer();
    const storage = storageWith({ "kuulas.fast": '{"speed":1.75}', other: "no" });
    const prefs = await loadPrefs(options(server, storage));
    assert.deepEqual(prefs.getJson("fast", null), { speed: 1.75 });
    await settle();
    assert.deepEqual(server.state.prefs, { "kuulas.fast": '{"speed":1.75}' });
  });
  test("does not import when the server already has settings", async () => {
    const server = fakeServer({ "kuulas.theme": "dark" });
    const storage = storageWith({ "kuulas.old": "stale" });
    const prefs = await loadPrefs(options(server, storage));
    assert.equal(prefs.get("old"), null);
  });
});
