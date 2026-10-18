import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  coalesceKey,
  patchBus,
  patchClip,
  patchSolo,
  patchTrack,
  splitClipsProvisional,
} from "../provisional.js";

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

describe("a split shows at once (before the server answers)", () => {
  const project = {
    rate: 48000,
    tracks: [
      {
        id: "t1",
        clips: [
          { id: "a", start: 0, offset: 100, length: 1000, fade_in: 50, fade_out: 60, muted: false },
          { id: "b", start: 2000, offset: 0, length: 500, fade_in: 0, fade_out: 0 },
        ],
      },
      { id: "t2", clips: [] },
    ],
  };

  test("a clip holding the frame becomes a left and a right piece covering the same audio", () => {
    const next = splitClipsProvisional(project, 400, ["a"]);
    const clips = next.tracks[0].clips;
    assert.equal(clips.length, 3);
    const left = clips.find((c) => c.id === "a");
    const right = clips.find((c) => c.id !== "a" && c.id !== "b");
    assert.deepEqual([left.start, left.offset, left.length], [0, 100, 400]);
    assert.deepEqual([right.start, right.offset, right.length], [400, 500, 600]);
    assert.equal(left.fade_in, 50);
    assert.equal(left.fade_out, 0);
    assert.equal(right.fade_in, 0);
    assert.equal(right.fade_out, 60);
  });

  test("clips in the list that do not hold the frame, and other clips, are left alone", () => {
    const next = splitClipsProvisional(project, 400, ["a", "b"]);
    assert.equal(next.tracks[0].clips.length, 3);
    assert.equal(next.tracks[0].clips.find((c) => c.id === "b").length, 500);
  });

  test("a frame on a clip's edge splits nothing, like the server", () => {
    assert.equal(splitClipsProvisional(project, 1000, ["a"]), project);
    assert.equal(splitClipsProvisional(project, 0, ["a"]), project);
  });

  test("the input is not changed and the new id is unique", () => {
    const before = JSON.stringify(project);
    const next = splitClipsProvisional(project, 400, ["a"]);
    assert.equal(JSON.stringify(project), before);
    const ids = next.tracks[0].clips.map((c) => c.id);
    assert.equal(new Set(ids).size, ids.length);
  });
});
