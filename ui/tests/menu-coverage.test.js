// Owner rule: every option can be found from the menus (discoverability).
// No exemption list: a command that is not built yet ("planned") still has
// its menu item, shown disabled.
import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { MENU, menuTargets } from "../menu-model.js";

test("every keymap command is an item in some menu", () => {
  const targets = new Set(menuTargets(MENU));
  const missing = DEFAULT_KEYMAP.map((entry) => entry.id).filter((id) => !targets.has(id));
  assert.deepEqual(missing, []);
});

test("no command appears twice in the same menu", () => {
  for (const top of MENU) {
    const ids = menuTargets([top]);
    assert.equal(new Set(ids).size, ids.length, `${top.id} repeats a command`);
  }
});

test("every menu title and submenu has a label key", () => {
  const walk = (items) =>
    items.flatMap((entry) =>
      entry.kind === "submenu" ? [entry.labelKey, ...(entry.items ? walk(entry.items) : [])] : [],
    );
  for (const top of MENU) {
    assert.ok(top.labelKey, top.id);
    for (const key of walk(top.items)) assert.ok(key, top.id);
  }
});
