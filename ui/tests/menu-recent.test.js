// File > Open Recent in the menu model: a submenu filled from the state, then Clear menu.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { MENU, menuTargets, resolveMenu } from "../menu-model.js";

const label = (key) => key;
const recent = [
  { path: "/p/A.kuulas", label: "A", detail: "1 hour ago", missing: false },
  { path: "/p/B.kuulas", label: "B", detail: "", missing: true },
];

function resolve(state) {
  const registry = createRegistry();
  const hasRecent = (s) => (s?.recentProjects?.length ?? 0) > 0;
  registry.register("app.open", () => {});
  registry.register("app.clear_recent", () => {}, { can: hasRecent });
  return resolveMenu({
    menu: MENU,
    entries: resolveKeymap(DEFAULT_KEYMAP, {}, "mac"),
    registry,
    state,
    label,
    platform: "mac",
    held: { alt: false, shift: false, mod: false },
  });
}
const openRecent = (menus) =>
  menus
    .find((m) => m.id === "file")
    .items.find((item) => item.kind === "submenu" && item.label === "menu.open_recent");

describe("File > Open Recent", () => {
  test("sits right under Open project and above Close project", () => {
    const shape = MENU.find((m) => m.id === "file").items.map((e) =>
      e.kind === "item" ? e.id : (e.labelKey ?? e.kind),
    );
    const at = shape.indexOf("app.open");
    assert.deepEqual(shape.slice(at, at + 3), [
      "app.open",
      "menu.open_recent",
      "app.close_project",
    ]);
  });

  test("lists the projects, then a separator and Clear menu", () => {
    const sub = openRecent(resolve({ recentProjects: recent }));
    assert.deepEqual(
      sub.items.map((item) => item.kind),
      ["item", "item", "separator", "item"],
    );
    const [a, b, , clear] = sub.items;
    assert.deepEqual([a.id, a.arg, a.label, a.enabled], ["app.open", "/p/A.kuulas", "A", true]);
    assert.match(a.tooltip, /\/p\/A\.kuulas/);
    assert.match(a.tooltip, /1 hour ago/);
    assert.equal(b.enabled, false, "a folder that is gone is greyed out");
    assert.deepEqual([clear.id, clear.enabled], ["app.clear_recent", true]);
  });

  test("with no projects: one greyed note and Clear menu greyed", () => {
    for (const state of [{}, { recentProjects: [] }]) {
      const sub = openRecent(resolve(state));
      assert.equal(sub.items[0].label, "menu.recent_none");
      assert.equal(sub.items[0].enabled, false);
      assert.equal(sub.items.at(-1).id, "app.clear_recent");
      assert.equal(sub.items.at(-1).enabled, false);
    }
  });

  test("the menu-coverage targets still name Clear menu", () => {
    assert.ok(menuTargets(MENU).includes("app.clear_recent"));
  });
});

describe("the new File and View items", () => {
  test("Close project, Preferences and Minimise are in menus", () => {
    const ids = menuTargets(MENU);
    for (const id of ["app.close_project", "app.preferences", "app.minimise"]) {
      assert.ok(ids.includes(id), id);
    }
    const file = menuTargets([MENU.find((m) => m.id === "file")]);
    assert.ok(file.includes("app.preferences"));
    assert.ok(menuTargets([MENU.find((m) => m.id === "view")]).includes("app.minimise"));
  });
});
