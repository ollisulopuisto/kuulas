import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  findCollisions,
  loadOverrides,
  parseOverrideText,
  resolveKeymap,
  saveOverrides,
  serializeOverrides,
  validateOverrides,
} from "../keymap-config.js";

const DATA = [
  { id: "a", keys: { mac: "B", other: "B" }, context: "timeline", labelKey: "cmd.a" },
  { id: "b", keys: { mac: ["X", "Mod+X"], other: ["X", "Mod+X"] }, context: "timeline", labelKey: "cmd.b" },
  { id: "c", keys: { mac: "B", other: "B" }, context: "transcript", labelKey: "cmd.c" },
  { id: "g", keys: { mac: "Mod+K", other: "Mod+K" }, context: "global", labelKey: "cmd.g" },
  { id: "t", keys: { mac: "Escape", other: "Escape" }, context: "text-field", labelKey: "cmd.t" },
  { id: "n", keys: { mac: null, other: null }, context: "global", labelKey: "cmd.n" },
];

describe("collisions", () => {
  test("the same key in the same context is reported with both ids", () => {
    const clash = resolveKeymap(DATA, { c: "X" }, "other");
    assert.deepEqual(findCollisions(clash), []); // transcript vs timeline
    const same = resolveKeymap(DATA, { a: "X" }, "other");
    assert.deepEqual(
      findCollisions(same).map((c) => [...c.ids].sort()),
      [["a", "b"]],
    );
  });

  test("a global or text-field key collides with the same key in any context", () => {
    const g = findCollisions(resolveKeymap(DATA, { a: "Mod+K" }, "other"));
    assert.deepEqual(g.map((c) => [...c.ids].sort()), [["a", "g"]]);
    const t = findCollisions(resolveKeymap(DATA, { c: "Escape" }, "other"));
    assert.deepEqual(t.map((c) => [...c.ids].sort()), [["c", "t"]]);
  });

  test("spelling does not hide a collision", () => {
    const entries = resolveKeymap(DATA, { a: "shift+alt+mod+r", c: "Alt+Shift+Mod+R" }, "other");
    assert.deepEqual(findCollisions(entries), []); // different contexts
    const same = resolveKeymap(DATA, { a: "shift+alt+mod+r", b: "Alt+Shift+Mod+R" }, "other");
    assert.equal(findCollisions(same).length, 1);
  });

  test("Ctrl is Mod off the Mac, a separate key on it", () => {
    const sheet = [
      { id: "p", keys: { mac: "Mod+J", other: "Mod+J" }, context: "global", labelKey: "x" },
      { id: "q", keys: { mac: "Ctrl+J", other: "Ctrl+J" }, context: "global", labelKey: "y" },
    ];
    assert.equal(findCollisions(resolveKeymap(sheet, {}, "other")).length, 1);
    assert.equal(findCollisions(resolveKeymap(sheet, {}, "mac")).length, 0);
  });
});

describe("override validation", () => {
  test("a good file is accepted whole", () => {
    const result = validateOverrides({ a: "Q", n: "Mod+Shift+N", b: null }, DATA, "other");
    assert.deepEqual(result.problems, []);
    assert.deepEqual(result.accepted, { a: "Q", n: "Mod+Shift+N", b: null });
  });

  test("unknown command, malformed combo and bad value are reported per entry", () => {
    const result = validateOverrides(
      { nope: "Q", a: "Mod+", b: "Hyper+X", c: 5, n: ["Q", ""] },
      DATA,
      "other",
    );
    const byId = Object.fromEntries(result.problems.map((p) => [p.id, p.code]));
    assert.deepEqual(byId, {
      nope: "unknown-command",
      a: "malformed-combo",
      b: "malformed-combo",
      c: "bad-value",
      n: "malformed-combo",
    });
    assert.deepEqual(result.accepted, {});
  });

  test("a collision is reported, names the other command, and the entry is not accepted", () => {
    const result = validateOverrides({ a: "X", n: "Q" }, DATA, "other");
    assert.deepEqual(result.problems.map((p) => [p.id, p.code, p.with]), [["a", "collision", ["b"]]]);
    assert.deepEqual(result.accepted, { n: "Q" });
  });

  test("swapping two keys is not a collision", () => {
    const sheet = [
      { id: "q", keys: { mac: "Q", other: "Q" }, context: "timeline", labelKey: "x" },
      { id: "w", keys: { mac: "W", other: "W" }, context: "timeline", labelKey: "y" },
    ];
    const result = validateOverrides({ q: "W", w: "Q" }, sheet, "other");
    assert.deepEqual(result.problems, []);
  });

  test("freeing a key (null) lets another command take it", () => {
    const result = validateOverrides({ a: null, c: "B", n: "B" }, DATA, "other");
    assert.deepEqual(result.problems.map((p) => p.id), ["n"]);
  });

  test("two overrides on one key both fail", () => {
    const result = validateOverrides({ a: "Q", n: "Q" }, DATA, "other");
    assert.deepEqual(result.problems.map((p) => p.id).sort(), ["a", "n"]);
  });

  test("something that is not an object is one problem", () => {
    for (const bad of [null, [], "x", 3]) {
      const result = validateOverrides(bad, DATA, "other");
      assert.deepEqual(result.problems.map((p) => p.code), ["not-object"]);
      assert.deepEqual(result.accepted, {});
    }
  });

  test("overrides replace both platform columns", () => {
    const entries = resolveKeymap(DATA, { a: "Q" }, "mac");
    assert.deepEqual(entries.find((e) => e.id === "a").raw, ["Q"]);
  });
});

describe("storage and files", () => {
  const memory = (initial = {}) => {
    const data = { ...initial };
    return {
      getItem: (k) => data[k] ?? null,
      setItem: (k, v) => {
        data[k] = v;
      },
      removeItem: (k) => {
        delete data[k];
      },
      data,
    };
  };
  const blocked = {
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

  test("save then load round-trips, and storage that throws is survivable", () => {
    const storage = memory();
    assert.equal(saveOverrides(storage, { a: "Q", b: null }), true);
    assert.deepEqual(loadOverrides(storage), { a: "Q", b: null });
    assert.equal(saveOverrides(blocked, { a: "Q" }), false);
    assert.deepEqual(loadOverrides(blocked), {});
    assert.deepEqual(loadOverrides(undefined), {});
  });

  test("garbage in storage reads as no overrides", () => {
    assert.deepEqual(loadOverrides(memory({ "kuulas.keymap": "{not json" })), {});
    assert.deepEqual(loadOverrides(memory({ "kuulas.keymap": "[1]" })), {});
  });

  test("an empty override set removes the stored key", () => {
    const storage = memory();
    saveOverrides(storage, { a: "Q" });
    saveOverrides(storage, {});
    assert.equal(storage.getItem("kuulas.keymap"), null);
  });

  test("the file is plain JSON and parses back", () => {
    const text = serializeOverrides({ a: "Q", b: null });
    assert.deepEqual(JSON.parse(text), { a: "Q", b: null });
    assert.deepEqual(parseOverrideText(text), { ok: true, value: { a: "Q", b: null } });
    assert.equal(parseOverrideText("{oops").ok, false);
  });
});
