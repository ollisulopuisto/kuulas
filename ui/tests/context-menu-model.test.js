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
    assert.deepEqual(ids(items), [
      "bus.collapse",
      "rename",
      "bus.mute",
      "-",
      "bus.role_speech",
      "bus.role_music",
      "bus.role_none",
      "bus.reapply_role",
      "-",
      "bus.ungroup",
    ]);
    assert.equal(items[0].labelKey, "cmd.bus.collapse");
    assert.equal(items[9].labelKey, "cmd.bus.ungroup");
  });
  test("enabled comes from the predicate", () => {
    const items = contextMenuItems({ kind: "bus", collapsed: false }, can(["rename"]));
    const enabled = Object.fromEntries(items.filter((i) => i.id).map((i) => [i.id, i.enabled]));
    assert.deepEqual(enabled, {
      "bus.collapse": false,
      rename: true,
      "bus.mute": false,
      "bus.role_speech": false,
      "bus.role_music": false,
      "bus.role_none": false,
      "bus.reapply_role": false,
      "bus.ungroup": false,
    });
  });
});

describe("track header menu", () => {
  test("rename, mute, solo, order, select, focus, role, then group into a bus", () => {
    const items = contextMenuItems({ kind: "track" }, can(["rename", "track.mute"]));
    assert.deepEqual(ids(items), [
      "rename",
      "track.mute",
      "track.solo",
      "-",
      "track.move_up",
      "track.move_down",
      "-",
      "edit.select_all_track",
      "view.focus",
      "-",
      "track.match_role",
      "track.role_speech",
      "track.role_music",
      "-",
      "track.group_into_bus",
    ]);
    assert.equal(items[1].enabled, true);
    assert.equal(items[2].enabled, false);
  });
});

describe("a track already on a bus", () => {
  test("offers Remove from bus, not Group into a bus", () => {
    const last = (target) => ids(contextMenuItems(target, can([]))).at(-1);
    assert.equal(last({ kind: "track", inBus: true }), "track.remove_from_bus");
    assert.equal(last({ kind: "track", inBus: false }), "track.group_into_bus");
  });
});

describe("role items are radio-style", () => {
  const marked = (items) => items.filter((i) => i.checked).map((i) => i.id);
  test("the bus's current role is marked; no role marks No role", () => {
    const bus = (role) => contextMenuItems({ kind: "bus", role }, can([]));
    assert.deepEqual(marked(bus("music")), ["bus.role_music"]);
    assert.deepEqual(marked(bus(null)), ["bus.role_none"]);
  });
  test("the track's choice is marked; Match shows the bus's role in brackets", () => {
    const track = (choice, busRole) =>
      contextMenuItems({ kind: "track", choice, busRole }, can(["track.match_role"]));
    assert.deepEqual(marked(track("match", "music")), ["track.match_role"]);
    assert.deepEqual(marked(track("speech", "music")), ["track.role_speech"]);
    const match = track("match", "music").find((i) => i.id === "track.match_role");
    assert.equal(match.labelKey, "cmd.track.match_role.with");
    assert.deepEqual(match.values, { role: { key: "ui.role.music" } });
    const plain = track("music", null).find((i) => i.id === "track.match_role");
    assert.equal(plain.labelKey, "cmd.track.match_role");
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
