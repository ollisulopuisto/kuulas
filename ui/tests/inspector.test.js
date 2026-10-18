import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { openSections, selectedClip, syncGroupOf } from "../inspector.js";
import { addBusForTrack } from "../inspector-track.js";

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

describe("inspector sections (density rework, 2026-10-18)", () => {
  test("Track, Bus, Level and Sync start open, the rest closed", () => {
    assert.deepEqual(openSections(null), {
      track: true,
      bus: true,
      level: true,
      fades: false,
      sync: true,
      source: false,
      details: false,
    });
  });

  test("what the user opened or closed is remembered; junk is ignored", () => {
    assert.deepEqual(openSections('{"fades":true,"level":false,"track":false}'), {
      track: false,
      bus: true,
      level: false,
      fades: true,
      sync: true,
      source: false,
      details: false,
    });
    assert.deepEqual(openSections("not json"), openSections(null));
    assert.deepEqual(openSections('{"level":"yes","bogus":true}'), openSections(null));
  });
});

describe("New bus from a track (header pop-up and inspector)", () => {
  const run = (answer) => {
    const sent = [];
    const created = [];
    addBusForTrack({ change: (edit) => sent.push(edit) }, "t1", (id) => created.push(id));
    answer?.(sent[0]);
    return { sent, created };
  };

  test("creates the bus for the track and reports the new bus once the server answers", () => {
    const { sent, created } = run((edit) =>
      edit.done({ project: { buses: [{ id: "b1" }, { id: "b2" }] } }),
    );
    assert.equal(sent[0].op, "add_bus");
    assert.deepEqual(sent[0].args, { track_ids: ["t1"] });
    assert.deepEqual(created, ["b2"]);
  });

  test("an answer without a bus calls nothing back", () => {
    const { created } = run((edit) => {
      edit.done({ project: { buses: [] } });
      edit.done(undefined);
    });
    assert.deepEqual(created, []);
  });
});
