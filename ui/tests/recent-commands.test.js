import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { MAX_RECENT, recentIds, recordRecent } from "../recent-commands.js";

describe("recordRecent", () => {
  test("newest first, no duplicates", () => {
    let list = [];
    for (const id of ["edit.split", "edit.cut", "edit.split"]) list = recordRecent(list, id);
    assert.deepEqual(list, ["edit.split", "edit.cut"]);
  });
  test("keeps the last eight", () => {
    let list = [];
    for (let n = 0; n < 12; n += 1) list = recordRecent(list, `edit.c${n}`);
    assert.equal(list.length, MAX_RECENT);
    assert.equal(MAX_RECENT, 8);
    assert.equal(list[0], "edit.c11");
  });
  test("navigation noise is not recorded", () => {
    for (const id of [
      "nav.start",
      "nav.forward_far",
      "view.zoom_in",
      "view.zoom_out",
      "view.back",
      "transport.shuttle_forward",
      "panel.next",
      "track.next",
      "palette.open",
      "edit.undo",
    ]) {
      assert.deepEqual(recordRecent(["edit.cut"], id), ["edit.cut"], id);
    }
  });
  test("view.fit and exports are recorded", () => {
    assert.deepEqual(recordRecent([], "view.fit"), ["view.fit"]);
    assert.deepEqual(recordRecent([], "export.regions"), ["export.regions"]);
  });
  test("junk is ignored", () => {
    assert.deepEqual(recordRecent(["a.b"], 5), ["a.b"]);
    assert.deepEqual(recordRecent("junk", "a.b"), ["a.b"]);
  });
});

describe("recentIds", () => {
  test("drops unknown commands and ones that cannot apply", () => {
    const registry = createRegistry();
    registry.register("edit.cut", () => {}, { can: (s) => s.sel });
    registry.register("edit.split", () => {});
    const ids = recentIds(["gone", "edit.cut", "edit.split"], { registry, state: { sel: false } });
    assert.deepEqual(ids, ["edit.split"]);
  });
  test("a non-list is empty", () => {
    assert.deepEqual(recentIds(null, { registry: createRegistry(), state: {} }), []);
  });
});

describe("registry.onRun", () => {
  test("is told about each command that ran, not those that did not", () => {
    const registry = createRegistry();
    const seen = [];
    registry.onRun((id) => seen.push(id));
    registry.register("a.b", () => {});
    registry.register("c.d", () => {}, { can: () => false });
    registry.run("a.b", null, {});
    registry.run("c.d", null, {});
    registry.run("nope", null, {});
    assert.deepEqual(seen, ["a.b"]);
  });
});
