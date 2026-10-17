import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { cheatSheetData } from "../cheatsheet.js";
import { resolveKeymap } from "../keymap-config.js";

const DATA = [
  { id: "t1", keys: { mac: "B", other: "B" }, context: "timeline", labelKey: "cmd.t1" },
  { id: "x1", keys: { mac: "Backspace", other: "Backspace" }, context: "transcript", labelKey: "cmd.x1" },
  { id: "g1", keys: { mac: "Space", other: "Space" }, context: "global", labelKey: "cmd.g1" },
  { id: "s1", keys: { mac: "Alt+Mod+ArrowLeft", other: "Alt+Mod+ArrowLeft" }, context: "side", labelKey: "cmd.s1" },
  { id: "e1", keys: { mac: "Escape", other: "Escape" }, context: "text-field", labelKey: "cmd.e1" },
];
const labels = { "cmd.t1": "Split", "cmd.x1": "Cut words", "cmd.g1": "Play", "cmd.s1": "Collapse", "cmd.e1": "Back" };
const label = (k) => labels[k] ?? k;
const fmt = (c) => `<${c}>`;

function build(overrides = {}, query = "") {
  const registry = createRegistry();
  registry.register("g1", () => {});
  registry.planned("t1");
  return cheatSheetData({
    entries: resolveKeymap(DATA, overrides, "other"),
    registry,
    query,
    label,
    format: fmt,
    platform: "other",
  });
}

describe("cheat sheet data", () => {
  test("is grouped by context in a fixed order, global first", () => {
    const groups = build();
    assert.deepEqual(groups.map((g) => g.context), ["global", "timeline", "transcript", "side", "text-field"]);
  });

  test("rows carry the label, the user's keys and the planned flag", () => {
    const groups = build({ t1: "Q" });
    const timeline = groups.find((g) => g.context === "timeline");
    assert.deepEqual(timeline.rows, [{ id: "t1", label: "Split", keys: ["<Q>"], planned: true }]);
  });

  test("an unbound command shows no keys", () => {
    const groups = build({ t1: null });
    assert.deepEqual(groups.find((g) => g.context === "timeline").rows[0].keys, []);
  });

  test("the search matches labels and key text, and drops empty groups", () => {
    const byLabel = build({}, "cut");
    assert.deepEqual(byLabel.map((g) => g.context), ["transcript"]);
    const byKey = build({}, "Backsp");
    assert.deepEqual(byKey.map((g) => g.rows[0].id), ["x1"]);
    assert.deepEqual(build({}, "zzzz"), []);
  });
});
