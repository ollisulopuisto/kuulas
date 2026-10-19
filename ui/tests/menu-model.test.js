import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { setCatalogs, setLanguageNow } from "../i18n.js";
import { resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import {
  findItem,
  fitMenus,
  MENU,
  menuTargets,
  moveItem,
  moveMenu,
  overflowMenu,
  resolveMenu,
} from "../menu-model.js";

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
  registry.register("view.clip_words", () => {});
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
  test("has the expected menus in order, and names only known commands", () => {
    assert.deepEqual(
      MENU.map((m) => m.id),
      ["file", "edit", "track", "playback", "view", "help"],
    );
    const ids = new Set(DEFAULT_KEYMAP.map((e) => e.id));
    for (const id of menuTargets(MENU)) assert.ok(ids.has(id), id);
  });

  test("View has fit tracks and auto-fit", () => {
    const view = MENU.find((top) => top.id === "view");
    const ids = menuTargets([view]);
    assert.ok(ids.includes("view.fit_tracks"));
    assert.ok(ids.includes("view.auto_fit_tracks"));
  });

  test("View has Words in clips, shown checked unless switched off", () => {
    const view = MENU.find((top) => top.id === "view");
    assert.ok(menuTargets([view]).includes("view.clip_words"));
    const find2 = (state) => find(make({ state }), "view.clip_words");
    assert.equal(find2({ showClipWords: true }).checked, true);
    assert.equal(find2({ showClipWords: false }).checked, false);
    assert.equal(find2({}).checked, true);
    assert.equal(find(make(), "edit.undo").checked, undefined);
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

  test("Help for this follows the search field in Help, always enabled, with its key and a remap", () => {
    // WP75: the search field is the first item of Help; Help for this is the first command after it.
    const items = (overrides) =>
      make({ overrides })
        .find((m) => m.id === "help")
        .items.filter((i) => i.kind === "item");
    assert.equal(items()[0].id, "help.open");
    assert.equal(items()[0].label, "Help for this");
    assert.equal(items()[0].enabled, true);
    assert.equal(items()[0].keys, "F1");
    assert.equal(items({ "help.open": "F3" })[0].keys, "F3");
    assert.equal(items()[1].id, "help.keys");
  });

  test("the search field is the first item of Help, a command with its key (WP75)", () => {
    const help = make().find((m) => m.id === "help");
    assert.equal(help.items[0].kind, "search");
    assert.equal(help.items[0].id, "help.search");
    assert.equal(help.items[0].keys, "Ctrl+Shift+K");
    assert.ok(menuTargets(MENU).includes("help.search"), "the coverage test sees it as in a menu");
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
    const held = find(make({ held: { shift: true }, planned: ["edit.split_all"] }), "edit.split");
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

describe("menus that do not fit the bar", () => {
  const widths = [50, 50, 50, 50]; // gap 4 between titles; "…" button 30 wide
  const fit = (available) => fitMenus(widths, available, { gap: 4, overflowWidth: 30 });

  test("all menus are shown when they fit, with no overflow button", () => {
    assert.equal(fit(212), 4); // 4 * 50 + 3 * 4
    assert.equal(fit(1000), 4);
  });

  test("when they do not fit, the last ones move behind the overflow button", () => {
    assert.equal(fit(211), 3); // 3 * 50 + 2 * 4 + 4 + 30 = 192
    assert.equal(fit(191), 2); // 2 * 50 + 4 + 4 + 30 = 138 fits, 3 does not
    assert.equal(fit(137), 1);
    assert.equal(fit(0), 0);
  });

  test("an empty bar and a negative width are safe", () => {
    assert.equal(fitMenus([], 100, { gap: 4, overflowWidth: 30 }), 0);
    assert.equal(fit(-5), 0);
  });

  test("the overflow menu holds the hidden menus, each under a caption, and keys skip the captions", () => {
    const menus = [
      { id: "a", label: "A", items: [{ kind: "item", id: "a.1", label: "One" }] },
      {
        id: "b",
        label: "B",
        items: [
          { kind: "item", id: "b.1", label: "Two" },
          { kind: "submenu", label: "More", items: [] },
        ],
      },
      { id: "c", label: "C", items: [{ kind: "item", id: "c.1", label: "Three" }] },
    ];
    const more = overflowMenu(menus.slice(1), "…");
    assert.equal(more.label, "…");
    assert.deepEqual(
      more.items.map((i) => i.kind + (i.caption ?? i.id ?? i.label)),
      ["separatorB", "itemb.1", "submenuMore", "separatorC", "itemc.1"],
    );
    assert.equal(moveItem(more.items, -1, 1), 1); // first real item, not the caption
    assert.equal(moveItem(more.items, 2, 1), 4);
  });
});

describe("finding an item in the resolved menus (Alt+Enter in Help search)", () => {
  test("a top-level item gives its menu and position", () => {
    const menus = make();
    const at = findItem(menus, "edit.undo");
    assert.equal(menus[at.top].id, "edit");
    assert.equal(menus[at.top].items[at.item].baseId, "edit.undo");
    assert.equal(at.sub, -1);
  });
  test("an item inside a submenu gives the submenu's position and its own", () => {
    const menus = make();
    const at = findItem(menus, "export.subtitles_srt");
    assert.equal(menus[at.top].id, "file");
    const sub = menus[at.top].items[at.item];
    assert.equal(sub.kind, "submenu");
    assert.equal(sub.items[at.sub].baseId, "export.subtitles_srt");
  });
  test("a command in no menu, or an alias, is not found", () => {
    assert.equal(findItem(make(), "export.mix_wav"), null);
    assert.equal(findItem(make(), "no.such"), null);
  });
  test("it also finds an item inside the overflow menu", () => {
    const menus = make();
    const more = overflowMenu(menus.slice(1), "…");
    const shown = [menus[0], more];
    const at = findItem(shown, "edit.undo");
    assert.equal(shown[at.top].id, "overflow");
    assert.equal(shown[at.top].items[at.item].baseId, "edit.undo");
  });
});
