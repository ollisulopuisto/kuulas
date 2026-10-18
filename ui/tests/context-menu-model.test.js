import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { contextMenuItems, stepItem } from "../context-menu-model.js";

const can = (yes) => (id) => yes.includes(id);
const ids = (items) => items.map((item) => item.id ?? "-");

describe("bus header menu", () => {
  test("collapse for an expanded bus, expand for a collapsed one", () => {
    assert.equal(
      contextMenuItems({ kind: "bus", collapsed: false }, can([]))[0].id,
      "bus.collapse",
    );
    assert.equal(contextMenuItems({ kind: "bus", collapsed: true }, can([]))[0].id, "bus.expand");
  });
  test("collapse, rename, mute, ungroup; labels are the command labels", () => {
    const items = contextMenuItems({ kind: "bus", collapsed: false }, can([]));
    assert.deepEqual(ids(items), ["bus.collapse", "rename", "bus.mute", "-", "bus.ungroup"]);
    assert.deepEqual(
      items.filter((i) => i.id).map((i) => i.labelKey),
      ["cmd.bus.collapse", "cmd.rename", "cmd.bus.mute", "cmd.bus.ungroup"],
    );
  });
  test("enabled comes from the predicate", () => {
    const items = contextMenuItems({ kind: "bus", collapsed: false }, can(["rename"]));
    const enabled = Object.fromEntries(items.filter((i) => i.id).map((i) => [i.id, i.enabled]));
    assert.deepEqual(enabled, {
      "bus.collapse": false,
      rename: true,
      "bus.mute": false,
      "bus.ungroup": false,
    });
  });
});

describe("track header menu", () => {
  test("rename, mute, solo, group into a new bus, remove from bus", () => {
    const items = contextMenuItems({ kind: "track" }, can(["rename", "track.mute"]));
    assert.deepEqual(ids(items), [
      "rename",
      "track.mute",
      "track.solo",
      "-",
      "track.group_into_bus",
      "track.remove_from_bus",
    ]);
    assert.equal(items[1].enabled, true);
    assert.equal(items[2].enabled, false);
  });
});

describe("keyboard stepping", () => {
  const items = [
    { id: "a", enabled: true },
    { separator: true },
    { id: "b", enabled: false },
    { id: "c", enabled: true },
  ];
  test("skips separators and disabled items, wraps around", () => {
    assert.equal(stepItem(items, 0, 1), 3);
    assert.equal(stepItem(items, 3, 1), 0);
    assert.equal(stepItem(items, 0, -1), 3);
    assert.equal(stepItem(items, 3, -1), 0);
  });
  test("from nowhere: Down takes the first, Up the last; nothing enabled gives -1", () => {
    assert.equal(stepItem(items, -1, 1), 0);
    assert.equal(stepItem(items, -1, -1), 3);
    assert.equal(stepItem([{ id: "x", enabled: false }], -1, 1), -1);
  });
});
