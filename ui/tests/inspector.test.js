import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { selectedClip, syncGroupOf } from "../inspector.js";

// The server sends sync-group members as { mediaId: origin } (SyncGroup.to_dict).
const project = {
  media: [{ id: "m1", name: "a.wav" }],
  tracks: [{ id: "t1", clips: [{ id: "c1", media: "m1" }] }],
  sync_groups: [{ id: "g1", main: "m1", members: { m1: 0, m2: 5 } }],
};

describe("inspector lookups", () => {
  test("the sync group is found from the members object", () => {
    assert.equal(syncGroupOf(project, "m2").id, "g1");
    assert.equal(syncGroupOf(project, "zz"), null);
    assert.equal(syncGroupOf({ ...project, sync_groups: undefined }, "m1"), null);
  });

  test("only a single selection is inspected", () => {
    const base = { project, selection: new Set(["c1"]) };
    assert.equal(selectedClip(base).media.name, "a.wav");
    assert.equal(selectedClip(base).track.id, "t1", "the track gives the header colour");
    assert.equal(selectedClip({ ...base, selection: new Set(["c1", "x"]) }), null);
    assert.equal(selectedClip({ ...base, selection: new Set(["gone"]) }), null);
  });
});
