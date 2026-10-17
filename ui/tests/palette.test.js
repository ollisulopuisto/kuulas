import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { resolveKeymap } from "../keymap-config.js";
import { moveSelection, paletteRows } from "../palette.js";

const DATA = [
  { id: "edit.undo", keys: { mac: "Mod+Z", other: "Mod+Z" }, context: "global", labelKey: "cmd.undo" },
  { id: "view.fit", keys: { mac: "Shift+Z", other: "Shift+Z" }, context: "global", labelKey: "cmd.fit" },
  { id: "edit.split", keys: { mac: "B", other: "B" }, context: "timeline", labelKey: "cmd.split" },
  { id: "keymap.reset", keys: { mac: null, other: null }, context: "global", labelKey: "cmd.reset" },
];
const LABELS = { "cmd.undo": "Undo", "cmd.fit": "Fit to edit", "cmd.split": "Split", "cmd.reset": "Reset keys" };
const label = (key) => LABELS[key] ?? key;
const fmt = (combo, platform) => `${platform}:${combo}`;

function setup(state = { canUndo: true }) {
  const registry = createRegistry();
  registry.register("edit.undo", () => {}, { can: (s) => s.canUndo });
  registry.register("view.fit", () => {});
  registry.register("keymap.reset", () => {});
  registry.planned("edit.split");
  const entries = resolveKeymap(DATA, {}, "other");
  return (query) => paletteRows({ entries, registry, state, query, label, format: fmt, platform: "other" });
}

describe("palette rows", () => {
  test("lists every command with its current keys, runnable ones first", () => {
    const rows = setup()("");
    assert.deepEqual(rows.map((r) => r.id), ["edit.undo", "view.fit", "keymap.reset", "edit.split"]);
    assert.deepEqual(rows[0].keys, ["other:Mod+Z"]);
    assert.deepEqual(rows[2].keys, []);
    assert.equal(rows[3].planned, true);
    assert.equal(rows[0].enabled, true);
  });

  test("a command that cannot apply now is listed but not enabled", () => {
    const rows = setup({ canUndo: false })("undo");
    assert.equal(rows[0].id, "edit.undo");
    assert.equal(rows[0].enabled, false);
  });

  test("the query filters by label and carries the matched letters", () => {
    const rows = setup()("fit");
    assert.deepEqual(rows.map((r) => r.id), ["view.fit"]);
    assert.deepEqual(rows[0].indices, [0, 1, 2].map((i) => i + 7));
  });

  test("a query nothing matches gives no rows", () => {
    assert.deepEqual(setup()("qqq"), []);
  });

  test("user overrides show up as the key", () => {
    const registry = createRegistry();
    registry.register("edit.undo", () => {});
    const entries = resolveKeymap(DATA, { "edit.undo": "Q" }, "other");
    const rows = paletteRows({ entries, registry, state: {}, query: "undo", label, format: fmt, platform: "other" });
    assert.deepEqual(rows[0].keys, ["other:Q"]);
  });
});

describe("selection", () => {
  test("moves and wraps", () => {
    assert.equal(moveSelection(0, 1, 3), 1);
    assert.equal(moveSelection(2, 1, 3), 0);
    assert.equal(moveSelection(0, -1, 3), 2);
    assert.equal(moveSelection(0, 1, 0), -1);
  });
});
