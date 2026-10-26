import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { ICONS } from "../icons.js";
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
  test("every default button has an icon that exists, so icon-only mode is never empty", () => {
    for (const id of DEFAULT_LAYOUT) {
      const icon = TOOLBAR_ICONS[id];
      assert.ok(typeof icon === "string", `${id} has an icon`);
      assert.ok(icon in ICONS, `${id}: icon ${icon} is in icons.js`);
    }
  });
});

describe("the Auto-Silence badge", () => {
  const project = {
    tracks: [
      {
        id: "a",
        clips: [
          {
            id: 1,
            auto_silence: [
              [0, 10],
              [20, 30],
            ],
          },
          { id: 2 },
        ],
      },
      { id: "b", clips: [{ id: 3, auto_silence: [[5, 9]] }] },
    ],
  };
  const items = (state) =>
    toolbarItems({
      layout: ["app.auto_silence", "edit.undo"],
      registry: registry(["app.auto_silence", "edit.undo"]),
      state,
      t,
      keyOf,
    });

  test("counts the silent stretches of every clip", () => {
    assert.equal(items({ project })[0].badge, "3");
  });

  test("no stretches, or no project, no badge", () => {
    assert.equal(items({ project: null })[0].badge, null);
    assert.equal(items({ project: { tracks: [{ clips: [{ id: 1 }] }] } })[0].badge, null);
  });

  test("a big count is capped so it fits the button", () => {
    const many = {
      tracks: [{ clips: [{ auto_silence: Array.from({ length: 250 }, (_, i) => [i, i]) }] }],
    };
    assert.equal(items({ project: many })[0].badge, "99+");
  });

  test("only that button has a badge, and the badge never changes the order", () => {
    assert.equal(items({ project })[1].badge, null);
    assert.deepEqual(
      items({ project }).map((i) => i.id),
      ["app.auto_silence", "edit.undo"],
    );
  });
});

describe("the icons of the former stand-ins", () => {
  test("every default button has an icon of its own", () => {
    const used = DEFAULT_LAYOUT.map((id) => TOOLBAR_ICONS[id]);
    assert.equal(new Set(used).size, used.length);
    for (const id of [
      "app.transcribe",
      "app.auto_silence",
      "sync.resync_range",
      "export.automix",
    ]) {
      assert.ok(!["rename", "lock", "reset", "layers"].includes(TOOLBAR_ICONS[id]), id);
    }
  });
});
