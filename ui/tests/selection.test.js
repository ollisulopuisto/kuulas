import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  clipsAround,
  currentTrack,
  markedRange,
  selectAllIds,
  selectedClips,
} from "../selection.js";

const S = 48000;
const clip = (id, start, seconds, extra = {}) => ({
  id,
  start: start * S,
  length: seconds * S,
  muted: false,
  ...extra,
});
const project = {
  rate: S,
  tracks: [
    { id: "A", clips: [clip("a1", 0, 10), clip("a2", 12, 8)] },
    { id: "V", clips: [clip("v1", 0, 10)] },
    { id: "M", clips: [] },
  ],
};
const base = (extra = {}) => ({
  project,
  selection: new Set(),
  focusTrack: "A",
  focusBus: null,
  playhead: 4 * S,
  inPoint: null,
  outPoint: null,
  ...extra,
});

describe("what the in/out range means", () => {
  test("both points set: the range, whichever order they were set in", () => {
    assert.deepEqual(markedRange(base({ inPoint: 2 * S, outPoint: 6 * S })), {
      start: 2 * S,
      end: 6 * S,
    });
    assert.deepEqual(markedRange(base({ inPoint: 6 * S, outPoint: 2 * S })), {
      start: 2 * S,
      end: 6 * S,
    });
  });
  test("one point, or two equal points: no range", () => {
    assert.equal(markedRange(base({ inPoint: 2 * S })), null);
    assert.equal(markedRange(base({ outPoint: 2 * S })), null);
    assert.equal(markedRange(base({ inPoint: S, outPoint: S })), null);
    assert.equal(markedRange(base()), null);
  });
});

describe("what the selection means", () => {
  test("selected clips come with their track, in track order", () => {
    const got = selectedClips(base({ selection: new Set(["v1", "a2"]) }));
    assert.deepEqual(
      got.map((c) => [c.clip.id, c.trackId]),
      [
        ["a2", "A"],
        ["v1", "V"],
      ],
    );
  });
  test("ids that no longer exist are ignored; no project is an empty selection", () => {
    assert.deepEqual(selectedClips(base({ selection: new Set(["gone"]) })), []);
    assert.deepEqual(selectedClips({ project: null, selection: new Set(["a1"]) }), []);
  });
  test("select all: this track, or every track", () => {
    assert.deepEqual(selectAllIds(base(), false), ["a1", "a2"]);
    assert.deepEqual(selectAllIds(base({ focusTrack: "V" }), false), ["v1"]);
    assert.deepEqual(selectAllIds(base(), true), ["a1", "a2", "v1"]);
    assert.deepEqual(selectAllIds(base({ focusTrack: null }), false), []);
  });
});

describe("the current track", () => {
  test("the focused track; a focused bus row means no current track", () => {
    assert.equal(currentTrack(base()), "A");
    assert.equal(currentTrack(base({ focusBus: "bus1" })), null);
  });
  test("with no focus, the one track the selection sits on", () => {
    assert.equal(currentTrack(base({ focusTrack: null, selection: new Set(["v1"]) })), "V");
    assert.equal(currentTrack(base({ focusTrack: null, selection: new Set(["v1", "a1"]) })), null);
  });
  test("a focused track that is gone counts as none", () => {
    assert.equal(currentTrack(base({ focusTrack: "zzz" })), null);
  });
});

describe("clips around the playhead", () => {
  test("strictly inside: an edge is not inside", () => {
    assert.deepEqual(clipsAround(project, 4 * S, "A"), ["a1"]);
    assert.deepEqual(clipsAround(project, 10 * S, "A"), []);
    assert.deepEqual(clipsAround(project, 0, "A"), []);
  });
  test("all tracks with null", () => {
    assert.deepEqual(clipsAround(project, 4 * S, null), ["a1", "v1"]);
  });
});
