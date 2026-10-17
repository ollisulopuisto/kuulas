import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { coalesceKey, patchBus, patchClip, patchSolo, patchTrack } from "../provisional.js";

const project = () =>
  Object.freeze({
    tracks: Object.freeze([
      Object.freeze({
        id: "t1",
        gain_db: 0,
        pan: 0,
        mute: false,
        solo: false,
        clips: Object.freeze([Object.freeze({ id: "c1", gain_db: 0, muted: false })]),
      }),
      Object.freeze({ id: "t2", gain_db: 0, pan: 0, mute: false, solo: false, clips: [] }),
    ]),
    buses: Object.freeze([Object.freeze({ id: "b1", gain_db: 0, mute: false })]),
  });

describe("provisional results", () => {
  test("patchTrack changes one track and leaves the input alone", () => {
    const before = project();
    const after = patchTrack(before, "t1", { gain_db: -6 });
    assert.equal(after.tracks[0].gain_db, -6);
    assert.equal(before.tracks[0].gain_db, 0);
    assert.equal(after.tracks[1], before.tracks[1], "other tracks are shared, not copied");
  });

  test("pan is clamped the way the server clamps it", () => {
    assert.equal(patchTrack(project(), "t1", { pan: 3 }).tracks[0].pan, 1);
  });

  test("patchBus and patchClip do the same for buses and clips", () => {
    assert.equal(patchBus(project(), "b1", { mute: true }).buses[0].mute, true);
    assert.equal(patchClip(project(), "c1", { gain_db: 3 }).tracks[0].clips[0].gain_db, 3);
  });

  test("an unknown id changes nothing", () => {
    const before = project();
    assert.equal(patchTrack(before, "nope", { gain_db: 1 }), before);
    assert.equal(patchClip(before, "nope", { gain_db: 1 }), before);
  });

  test("exclusive solo clears the others; soloing the only one again clears it", () => {
    const one = patchSolo(project(), "t1", true);
    assert.deepEqual(
      one.tracks.map((t) => t.solo),
      [true, false],
    );
    const two = patchSolo(one, "t2", true);
    assert.deepEqual(
      two.tracks.map((t) => t.solo),
      [false, true],
    );
    assert.deepEqual(
      patchSolo(two, "t2", true).tracks.map((t) => t.solo),
      [false, false],
    );
  });

  test("additive solo toggles one track and leaves the rest", () => {
    const both = patchSolo(patchSolo(project(), "t1", false), "t2", false);
    assert.deepEqual(
      both.tracks.map((t) => t.solo),
      [true, true],
    );
  });

  test("a drag is one undo step: the key names the control and the thing", () => {
    assert.equal(coalesceKey("track", "gain", "t1"), "track-gain-t1");
    assert.equal(coalesceKey("bus", "pan", "b1"), "bus-pan-b1");
    assert.equal(coalesceKey("clip", "gain_db", "c1"), "clip-gain_db-c1");
  });
});
