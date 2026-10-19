// Owner rule: every option can be found from the menus (discoverability).
// A command that is not built yet ("planned") still has its menu item, shown disabled.
// Two documented allowances (WP74, owner), nothing else:
//   PALETTE_ONLY  the per-format export commands (export.mix_<f>, export.tracks_<f>): the
//                 "(options)…" dialogs choose any format; they stay in the command palette.
//   MENU_ALIASES  a command shown through its twin (Previous / Next stop: nav.* and
//                 transcript.*), so the menu lists the action once.
import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { MENU, MENU_ALIASES, menuTargets, PALETTE_ONLY } from "../menu-model.js";

test("every keymap command is an item in some menu, bar the documented allowances", () => {
  const targets = new Set(menuTargets(MENU));
  const allowed = new Set([...PALETTE_ONLY, ...Object.keys(MENU_ALIASES)]);
  const missing = DEFAULT_KEYMAP.map((entry) => entry.id).filter(
    (id) => !targets.has(id) && !allowed.has(id),
  );
  assert.deepEqual(missing, []);
});

test("the allowances are exact: palette-only commands are in no menu, aliases point into one", () => {
  const targets = new Set(menuTargets(MENU));
  const ids = new Set(DEFAULT_KEYMAP.map((entry) => entry.id));
  assert.equal(PALETTE_ONLY.length, 14);
  for (const id of PALETTE_ONLY) {
    assert.ok(ids.has(id), `${id} is not a command`);
    assert.ok(!targets.has(id), `${id} is in a menu, so it needs no allowance`);
  }
  for (const [twin, shown] of Object.entries(MENU_ALIASES)) {
    assert.ok(ids.has(twin), twin);
    assert.ok(!targets.has(twin), `${twin} is in a menu, so it needs no alias`);
    assert.ok(targets.has(shown), `${shown} is not in a menu`);
  }
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
