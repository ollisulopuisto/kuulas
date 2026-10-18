import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { setCatalogs, setLanguageNow } from "../i18n.js";
import { resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { MENU, menuTargets, moveItem, moveMenu, resolveMenu } from "../menu-model.js";

const LABELS = {
  "menu.file": "File",
  "menu.edit": "Edit",
  "cmd.edit.undo": "Undo",
  "cmd.edit.redo": "Redo",
  "cmd.app.import": "Import…",
  "cmd.help.keys": "Keyboard shortcuts",
  "cmd.help.open": "Help for this",
  "hint.undo": "Take back the last change",
};
setCatalogs({
  en: { "key.ctrl": "Ctrl", "key.space": "Space", "key.shift": "Shift", "key.alt": "Alt" },
  fi: {},
});
setLanguageNow("en");
const label = (key) => LABELS[key] ?? key;

function make({ platform = "other", overrides = {}, state = {}, planned = [], held = {} } = {}) {
  const registry = createRegistry();
  registry.register("edit.undo", () => {}, { can: (s) => s.canUndo, hintKey: "hint.undo" });
  registry.register("edit.redo", () => {}, { can: (s) => s.canRedo });
  registry.register("app.import", () => {});
  registry.register("help.keys", () => {});
  registry.register("help.open", () => {});
  registry.register("edit.split", () => {});
  registry.register("edit.split_all", () => {});
  registry.planned(...planned);
  const entries = resolveKeymap(DEFAULT_KEYMAP, overrides, platform);
  return resolveMenu({
    menu: MENU,
    entries,
    registry,
    state,
    label,
    platform,
    held: { alt: false, shift: false, mod: false, ...held },
  });
}
const find = (menus, id) => {
  const walk = (items) =>
    items.flatMap((item) =>
      item.kind === "submenu" ? walk(item.items) : item.kind === "item" ? [item] : [],
    );
  return menus.flatMap((m) => walk(m.items)).find((i) => (i.baseId ?? i.id) === id);
};

describe("the menu data", () => {
  test("has File, Edit, Track, Markers, Narration, View and Help, and names only known commands", () => {
    assert.deepEqual(
      MENU.map((m) => m.id),
      ["file", "edit", "track", "markers", "narration", "view", "help"],
    );
    const ids = new Set(DEFAULT_KEYMAP.map((e) => e.id));
    for (const id of menuTargets(MENU)) assert.ok(ids.has(id), id);
  });

  test("Help has Keyboard shortcuts", () => {
    assert.ok(menuTargets(MENU).includes("help.keys"));
    assert.ok(menuTargets(MENU).includes("help.open"));
  });
});

describe("resolving a menu", () => {
  test("label, enabled flag and key text come from the registry and the keymap", () => {
    const menus = make({ state: { canUndo: true, canRedo: false } });
    const undo = find(menus, "edit.undo");
    assert.equal(undo.label, "Undo");
    assert.equal(undo.enabled, true);
    assert.equal(undo.keys, "Ctrl+Z");
    assert.equal(find(menus, "edit.redo").enabled, false);
  });

  test("a disabled item keeps its key", () => {
    const redo = find(make({ state: {} }), "edit.redo");
    assert.equal(redo.enabled, false);
    assert.equal(redo.keys, "Ctrl+Shift+Z");
  });

  test("Mac shows glyphs in Apple's order", () => {
    const menus = make({ platform: "mac", state: { canUndo: true, canRedo: true } });
    assert.equal(find(menus, "edit.undo").keys, "⌘Z");
    assert.equal(find(menus, "edit.redo").keys, "⇧⌘Z");
  });

  test("a remapped item shows the new key at once", () => {
    const menus = make({ overrides: { "edit.undo": "Alt+U" }, state: { canUndo: true } });
    assert.equal(find(menus, "edit.undo").keys, "Alt+U");
  });

  test("an unbound command shows no key", () => {
    const menus = make({ overrides: { "edit.undo": null }, state: { canUndo: true } });
    assert.equal(find(menus, "edit.undo").keys, "");
  });

  test("a planned command is shown, disabled", () => {
    const menus = make({ state: { canUndo: true }, planned: ["app.import"] });
    const item = find(menus, "app.import");
    assert.equal(item.enabled, false);
    assert.equal(item.planned, true);
  });

  test("the tooltip is the hint plus the key, or the label plus the key", () => {
    const menus = make({ state: { canUndo: true } });
    assert.equal(find(menus, "edit.undo").tooltip, "Take back the last change · Ctrl+Z");
    assert.equal(find(menus, "app.import").tooltip, "Import… · Ctrl+I");
    assert.equal(find(menus, "app.import").hint, "Import…");
  });

  test("separators and submenus survive resolution", () => {
    const menus = make();
    const help = menus.find((m) => m.id === "help");
    assert.ok(help.items.some((i) => i.kind === "submenu"));
    assert.ok(menus.find((m) => m.id === "edit").items.some((i) => i.kind === "separator"));
  });

  test("Help for this is first in Help, always enabled, with its key and a remap", () => {
    const items = (overrides) => make({ overrides }).find((m) => m.id === "help").items;
    assert.equal(items()[0].id, "help.open");
    assert.equal(items()[0].label, "Help for this");
    assert.equal(items()[0].enabled, true);
    assert.equal(items()[0].keys, "F1");
    assert.equal(items({ "help.open": "F3" })[0].keys, "F3");
    assert.equal(items()[1].id, "help.keys");
  });

  test("a menu title is its message key", () => {
    assert.equal(make()[0].label, "File");
  });
});

describe("held modifiers", () => {
  test("holding Shift swaps Edit's Split item for its Shift alternate, and back", () => {
    const base = find(make(), "edit.split");
    assert.equal(base.keys, "B");
    const held = find(make({ held: { shift: true } }), "edit.split");
    assert.equal(held.id, "edit.split_all");
    assert.equal(held.baseId, "edit.split");
    assert.equal(held.alternate, true);
    assert.equal(held.keys, "Shift+B");
    assert.equal(held.enabled, true);
    assert.equal(find(make({ held: {} }), "edit.split").keys, "B");
  });

  test("the alternate's own enabled state counts", () => {
    const held = find(
      make({ held: { shift: true }, planned: ["edit.split_all"] }),
      "edit.split",
    );
    assert.equal(held.id, "edit.split_all");
    assert.equal(held.enabled, false); // planned in this fixture
  });

  test("an item with no alternate for the held key stays as it is", () => {
    const item = find(make({ held: { shift: true }, state: { canUndo: true } }), "edit.undo");
    assert.equal(item.id, "edit.redo");
    const imp = find(make({ held: { alt: true } }), "app.import");
    assert.equal(imp.id, "app.import");
    assert.equal(imp.alternate, false);
  });
});

describe("keyboard navigation", () => {
  const items = [
    { kind: "item", id: "a" },
    { kind: "separator" },
    { kind: "item", id: "b" },
    { kind: "item", id: "c" },
  ];
  test("moves over separators and wraps", () => {
    assert.equal(moveItem(items, 0, 1), 2);
    assert.equal(moveItem(items, 3, 1), 0);
    assert.equal(moveItem(items, 0, -1), 3);
    assert.equal(moveItem(items, 2, -1), 0);
  });
  test("from nothing, Down goes to the first and Up to the last", () => {
    assert.equal(moveItem(items, -1, 1), 0);
    assert.equal(moveItem(items, -1, -1), 3);
  });
  test("an empty menu has no item", () => {
    assert.equal(moveItem([], -1, 1), -1);
  });
  test("Left and Right move between menus and wrap", () => {
    assert.equal(moveMenu(5, 4, 1), 0);
    assert.equal(moveMenu(5, 0, -1), 4);
    assert.equal(moveMenu(5, 2, 1), 3);
  });
});
