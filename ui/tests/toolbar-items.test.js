import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { SHORT_LABELS, TOOLBAR_ICONS, toolbarItems } from "../toolbar-items.js";
import { DEFAULT_LAYOUT } from "../toolbar-model.js";

const registry = (ready, canNot = []) => ({
  has: (id) => ready.includes(id),
  can: (id) => ready.includes(id) && !canNot.includes(id),
});
const t = (key) => `<${key}>`;
const keyOf = (id) => (id === "edit.undo" ? "Cmd+Z" : "");

describe("toolbarItems", () => {
  test("one item per layout entry, in the layout's order", () => {
    const layout = ["app.export", "edit.undo", "app.import"];
    const items = toolbarItems({ layout, registry: registry(layout), state: {}, t, keyOf });
    assert.deepEqual(
      items.map((item) => item.id),
      layout,
    );
  });

  test("a default button has a short label, and the tip has the full name and the key", () => {
    const [undo, redo] = toolbarItems({
      layout: ["edit.undo", "edit.redo"],
      registry: registry(["edit.undo", "edit.redo"]),
      state: {},
      t,
      keyOf,
    });
    assert.equal(undo.label, "<ui.rail.short.edit.undo>");
    assert.equal(undo.tip, "<cmd.edit.undo> (Cmd+Z)");
    assert.equal(redo.tip, "<cmd.edit.redo>", "no key, no brackets");
  });

  test("a pinned command with no short label shows its full name", () => {
    const [item] = toolbarItems({
      layout: ["edit.delete"],
      registry: registry(["edit.delete"]),
      state: {},
      t,
      keyOf,
    });
    assert.equal(item.label, "<cmd.edit.delete>");
  });

  test("a command that cannot run is disabled and stays in its place", () => {
    const layout = ["edit.undo", "edit.redo", "app.import"];
    const items = toolbarItems({
      layout,
      registry: registry(layout, ["edit.redo"]),
      state: {},
      t,
      keyOf,
    });
    assert.deepEqual(
      items.map((item) => [item.id, item.enabled]),
      [
        ["edit.undo", true],
        ["edit.redo", false],
        ["app.import", true],
      ],
    );
  });

  test("a command the registry does not know is shown, disabled, and not dropped", () => {
    const [item] = toolbarItems({
      layout: ["ghost.command"],
      registry: registry([]),
      state: {},
      t,
      keyOf,
    });
    assert.equal(item.enabled, false);
    assert.equal(item.label, "<cmd.ghost.command>");
  });

  test("nothing in the input but the layout can change the order", () => {
    const layout = [...DEFAULT_LAYOUT];
    const calm = toolbarItems({ layout, registry: registry(layout), state: {}, t, keyOf });
    const busy = toolbarItems({
      layout,
      registry: registry(layout, layout.slice(0, 5)),
      state: { playing: true, anything: 1 },
      t,
      keyOf,
    });
    assert.deepEqual(
      busy.map((item) => item.id),
      calm.map((item) => item.id),
    );
  });
});

describe("the short labels", () => {
  test("every default button has one", () => {
    for (const id of DEFAULT_LAYOUT) assert.ok(id in SHORT_LABELS, id);
  });
});

describe("the icons", () => {
  test("a command has an icon or null; a null is shown as text, never as an empty button", () => {
    for (const id of DEFAULT_LAYOUT) {
      assert.ok(id in TOOLBAR_ICONS, `${id} is listed`);
      const icon = TOOLBAR_ICONS[id];
      assert.ok(icon === null || typeof icon === "string", id);
    }
  });
});
