import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { deleteTarget, newMarkerId, registerMarkerCommands } from "../marker-commands.js";

const m = (id, start, extra = {}) => ({ id, name: id, start, kind: "marker", ...extra });

function setup(initial) {
  let state = { playhead: 0, inPoint: null, outPoint: null, ...initial };
  const registry = createRegistry();
  const calls = { edits: [], toasts: [], seeks: [], patches: [] };
  registerMarkerCommands(registry, {
    t: (key, values = {}) => `${key}${Object.keys(values).length ? JSON.stringify(values) : ""}`,
    makeId: () => "kNEW",
    app: {
      getState: () => state,
      patch: (patch) => {
        calls.patches.push(patch);
        state = { ...state, ...patch };
      },
      edit: (change) => {
        calls.edits.push(change);
        change.done?.({});
      },
      toast: (text, options) => calls.toasts.push([text, options]),
      seek: (frame) => calls.seeks.push(frame),
      jump: (frame) => calls.seeks.push(frame),
    },
  });
  return { registry, calls, get: () => state };
}

describe("marker.add", () => {
  test("adds a marker at the playhead, selects it, toasts with Undo", () => {
    const { registry, calls, get } = setup({ project: { markers: [] }, playhead: 4800 });
    assert.equal(registry.run("marker.add", null, get()), true);
    assert.deepEqual(calls.edits[0].args, {
      marker_id: "kNEW",
      name: "ui.markers.default.marker 1",
      start: 4800,
      kind: "marker",
    });
    assert.equal(calls.edits[0].op, "add_marker");
    assert.deepEqual(calls.patches.at(-1), { markerSelected: "kNEW" });
    assert.equal(calls.toasts[0][1].undo, true);
  });

  test("not where a marker already is, and not without a project", () => {
    const s = setup({ project: { markers: [m("a", 100)] }, playhead: 100 });
    assert.equal(s.registry.can("marker.add", s.get()), false);
    assert.equal(s.registry.can("marker.add", {}), false);
    assert.equal(s.registry.can("marker.add", { ...s.get(), playhead: 101 }), true);
  });
});

describe("region.from_selection", () => {
  test("makes a region of the in-out range", () => {
    const { registry, calls, get } = setup({
      project: { markers: [] },
      inPoint: 9000,
      outPoint: 3000,
    });
    registry.run("region.from_selection", null, get());
    assert.deepEqual(calls.edits[0].args, {
      marker_id: "kNEW",
      name: "ui.markers.default.region 1",
      start: 3000,
      kind: "region",
      end: 9000,
    });
  });

  test("needs both points", () => {
    const s = setup({ project: { markers: [] }, inPoint: 5, outPoint: null });
    assert.equal(s.registry.can("region.from_selection", s.get()), false);
    assert.equal(s.registry.run("region.from_selection", null, s.get()), false);
  });
});

describe("marker.next and marker.prev", () => {
  test("move the playhead to the next or previous start and pick it", () => {
    const s = setup({ project: { markers: [m("a", 100), m("b", 200)] }, playhead: 150 });
    s.registry.run("marker.next", null, s.get());
    s.registry.run("marker.prev", null, s.get());
    assert.deepEqual(s.calls.seeks, [200, 100]);
    assert.deepEqual(s.calls.patches[0], { markerSelected: "b" });
  });

  test("disabled at the ends", () => {
    const s = setup({ project: { markers: [m("a", 100)] }, playhead: 100 });
    assert.equal(s.registry.can("marker.next", s.get()), false);
    assert.equal(s.registry.can("marker.prev", s.get()), false);
  });
});

describe("marker.delete", () => {
  test("deletes the picked marker, else the one at the playhead", () => {
    assert.equal(
      deleteTarget({
        project: { markers: [m("a", 5), m("b", 9)] },
        playhead: 5,
        markerSelected: "b",
      }).id,
      "b",
    );
    assert.equal(deleteTarget({ project: { markers: [m("a", 5)] }, playhead: 5 }).id, "a");
    assert.equal(deleteTarget({ project: { markers: [m("a", 5)] }, playhead: 6 }), null);
  });

  test("sends delete_marker, clears the pick and toasts with Undo", () => {
    const s = setup({
      project: { markers: [m("a", 5)] },
      playhead: 0,
      markerSelected: "a",
    });
    s.registry.run("marker.delete", null, s.get());
    assert.deepEqual(s.calls.edits[0].args, { marker_id: "a" });
    assert.deepEqual(s.calls.patches.at(-1), { markerSelected: null });
    assert.equal(s.calls.toasts[0][1].undo, true);
  });
});

test("newMarkerId makes a 11 character id starting with k", () => {
  assert.match(newMarkerId(), /^k[0-9a-f]{10}$/);
  assert.match(
    newMarkerId(() => 0),
    /^k0{10}$/,
  );
});

test("the keyboard setup registers the marker commands (they would be planned otherwise)", async () => {
  const { readFileSync } = await import("node:fs");
  const source = readFileSync(new URL("../shell-keys.js", import.meta.url), "utf8");
  assert.match(source, /registerMarkerCommands\(registry/);
});
