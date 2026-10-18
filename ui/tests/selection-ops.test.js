import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  clipsInRange,
  forwardFromClip,
  forwardFromClips,
  forwardFromFrame,
  invert,
  rangeFromClips,
} from "../selection-ops.js";

const clip = (id, start, length, muted = false) => ({ id, start, length, muted });
const project = {
  tracks: [
    { id: "A", clips: [clip("a1", 0, 100), clip("a2", 200, 100), clip("a3", 400, 100, true)] },
    { id: "B", clips: [clip("b1", 50, 100), clip("b2", 300, 100)] },
  ],
};
const ids = (set) => [...set].sort();

describe("clipsInRange", () => {
  test("clips overlapping the range, on all tracks by default", () => {
    assert.deepEqual(ids(clipsInRange(project, { start: 90, end: 210 })), ["a1", "a2", "b1"]);
  });
  test("touching edges do not overlap", () => {
    assert.deepEqual(ids(clipsInRange(project, { start: 100, end: 200 })), ["b1"]);
  });
  test("limited to the given tracks; muted clips count", () => {
    assert.deepEqual(ids(clipsInRange(project, { start: 0, end: 1000 }, ["A"])), [
      "a1",
      "a2",
      "a3",
    ]);
  });
  test("no range, no project or no tracks give an empty set", () => {
    assert.equal(clipsInRange(project, null).size, 0);
    assert.equal(clipsInRange(null, { start: 0, end: 5 }).size, 0);
    assert.equal(clipsInRange(project, { start: 0, end: 1000 }, []).size, 0);
  });
});

describe("rangeFromClips", () => {
  test("first start to last end", () => {
    assert.deepEqual(rangeFromClips(project, new Set(["a2", "b1"])), { start: 50, end: 300 });
  });
  test("empty selection gives null", () => {
    assert.equal(rangeFromClips(project, new Set()), null);
  });
});

describe("forwardFromFrame", () => {
  test("every clip whose end is after the frame", () => {
    assert.deepEqual(ids(forwardFromFrame(project, 150)), ["a2", "a3", "b2"]);
  });
  test("a clip ending exactly at the frame is not included", () => {
    assert.deepEqual(ids(forwardFromFrame(project, 100)), ["a2", "a3", "b1", "b2"]);
  });
  test("a clip holding the frame is included", () => {
    assert.ok(forwardFromFrame(project, 250).has("a2"));
  });
  test("limited to tracks", () => {
    assert.deepEqual(ids(forwardFromFrame(project, 0, ["B"])), ["b1", "b2"]);
  });
  test("past everything is empty", () => {
    assert.equal(forwardFromFrame(project, 10_000).size, 0);
  });
});

describe("forwardFromClips", () => {
  test("per track: the selected clip and every later clip on that track", () => {
    assert.deepEqual(ids(forwardFromClips(project, new Set(["a2"]))), ["a2", "a3"]);
    assert.deepEqual(ids(forwardFromClips(project, new Set(["a2", "b2"]))), ["a2", "a3", "b2"]);
  });
  test("with several selected on one track the earliest counts", () => {
    assert.deepEqual(ids(forwardFromClips(project, new Set(["a1", "a3"]))), ["a1", "a2", "a3"]);
  });
  test("allTracks: the selected clips and every clip starting at or after the earliest selected start", () => {
    assert.deepEqual(ids(forwardFromClips(project, new Set(["a2"]), { allTracks: true })), [
      "a2",
      "a3",
      "b2",
    ]);
    // a1 began before b1 and merely overlaps it: it is not "after" b1.
    assert.deepEqual(ids(forwardFromClips(project, new Set(["b1"]), { allTracks: true })), [
      "a2",
      "a3",
      "b1",
      "b2",
    ]);
  });
  test("allTracks: a long clip that began earlier (a music bed) is not swept in", () => {
    const withBed = {
      tracks: [
        ...project.tracks,
        { id: "M", clips: [clip("bed", 0, 1000), clip("sting", 450, 10)] },
      ],
    };
    assert.deepEqual(ids(forwardFromClips(withBed, new Set(["a2"]), { allTracks: true })), [
      "a2",
      "a3",
      "b2",
      "sting",
    ]);
  });
  test("empty selection gives an empty set", () => {
    assert.equal(forwardFromClips(project, new Set()).size, 0);
    assert.equal(forwardFromClips(project, new Set(), { allTracks: true }).size, 0);
  });
});

describe("invert", () => {
  test("every clip not selected, on all tracks by default", () => {
    assert.deepEqual(ids(invert(project, new Set(["a1", "b2"]))), ["a2", "a3", "b1"]);
  });
  test("limited to tracks; selected clips elsewhere drop out", () => {
    assert.deepEqual(ids(invert(project, new Set(["a1", "b2"]), ["A"])), ["a2", "a3"]);
  });
  test("an empty selection inverts to everything, an empty project to nothing", () => {
    assert.equal(invert(project, new Set()).size, 5);
    assert.equal(invert({ tracks: [] }, new Set()).size, 0);
    assert.equal(invert(null, new Set()).size, 0);
  });
});

describe("forwardFromClip (Cmd+Alt+click)", () => {
  test("the clicked clip and every clip starting at or after it, on all tracks", () => {
    assert.deepEqual(ids(forwardFromClip(project, "a2")), ["a2", "a3", "b2"]);
  });
  test("an unknown clip selects nothing", () => {
    assert.equal(forwardFromClip(project, "nope").size, 0);
  });
});
