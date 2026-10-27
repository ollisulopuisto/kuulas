import assert from "node:assert/strict";
import { test } from "node:test";
import { outsideRail } from "../toolbar-model.js";
import { toolbarChoices } from "../toolbar-picker.js";

const entries = ["clip.mute", "edit.split", "app.planned"].map((id) => ({
  id,
  labelKey: `cmd.${id}`,
}));
const label = (key) =>
  ({
    "cmd.clip.mute": "Mykistä leike",
    "cmd.edit.split": "Jaa leike",
    "cmd.app.planned": "Planned",
  })[key] || key;
const registry = {
  has: () => true,
  status: (id) => (id === "app.planned" ? "planned" : "ready"),
  can: () => false,
};

test("the add picker offers ready commands even when they cannot currently run, without duplicates", () => {
  const rows = toolbarChoices({
    entries: [...entries, entries[0]],
    layout: ["edit.split"],
    registry,
    label,
    query: "",
  });
  assert.deepEqual(
    rows.map((row) => row.id),
    ["clip.mute"],
  );
});

test("toolbar search finds translated names and hints", () => {
  const rows = toolbarChoices({ entries, layout: [], registry, label, query: "mykista" });
  assert.deepEqual(
    rows.map((row) => row.id),
    ["clip.mute"],
  );
});

test("dragging away needs a clear margin beyond the rail, not a nearby reorder drop", () => {
  const rect = { left: 10, right: 130, top: 100, bottom: 700 };
  assert.equal(outsideRail(rect, 110, 300), false);
  assert.equal(outsideRail(rect, 150, 300), false);
  assert.equal(outsideRail(rect, 171, 300), true);
  assert.equal(outsideRail(rect, 70, 741), true);
});
