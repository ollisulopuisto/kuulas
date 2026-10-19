import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  clearTrackSelection,
  dimmedTracks,
  resolveScope,
  scopeChip,
  selectTrack,
  toggleScopeMode,
} from "../range-scope.js";

const project = {
  tracks: [
    { id: "a", name: "Olli" },
    { id: "b", name: "Kari" },
    { id: "c", name: "Music" },
    { id: "d", name: "Intro" },
  ],
};
const state = (extra = {}) => ({
  project,
  rangeMode: "all",
  trackSelection: new Set(),
  rangeTracks: new Set(),
  ...extra,
});

describe("resolveScope: the rectangle's tracks", () => {
  test("keyboard I/O with nothing selected is all tracks", () => {
    const scope = resolveScope(state());
    assert.deepEqual(scope.tracks, ["a", "b", "c", "d"]);
    assert.equal(scope.source, "all");
    assert.equal(scope.none, false);
  });

  test("a mouse-painted range in one lane is that lane only, several lanes those lanes", () => {
    assert.deepEqual(resolveScope(state({ rangeTracks: new Set(["b"]) })).tracks, ["b"]);
    const two = resolveScope(state({ rangeTracks: new Set(["c", "a"]) }));
    assert.deepEqual(two.tracks, ["a", "c"]);
    assert.equal(two.source, "lanes");
  });

  test("selected tracks override the default, also over painted lanes", () => {
    const scope = resolveScope(
      state({
        rangeMode: "selected",
        trackSelection: new Set(["d", "a"]),
        rangeTracks: new Set(["b"]),
      }),
    );
    assert.deepEqual(scope.tracks, ["a", "d"]);
    assert.equal(scope.source, "selected");
  });

  test("selected-only mode with no track selected touches nothing and says so", () => {
    const scope = resolveScope(state({ rangeMode: "selected" }));
    assert.deepEqual(scope.tracks, []);
    assert.equal(scope.none, true);
    assert.equal(scope.source, "none");
  });

  test("ids of tracks that no longer exist are ignored", () => {
    const scope = resolveScope(state({ rangeTracks: new Set(["gone"]) }));
    assert.equal(scope.source, "all");
    const none = resolveScope(state({ rangeMode: "selected", trackSelection: new Set(["gone"]) }));
    assert.equal(none.none, true);
  });

  test("all mode wins over a stale selection (E switched back to all tracks)", () => {
    const scope = resolveScope(state({ rangeMode: "all", trackSelection: new Set(["a"]) }));
    assert.equal(scope.tracks.length, 4);
  });
});

describe("selecting track headers", () => {
  test("a click selects that track and switches to selected tracks only", () => {
    const patch = selectTrack(state(), "b");
    assert.deepEqual([...patch.trackSelection], ["b"]);
    assert.equal(patch.rangeMode, "selected");
  });

  test("a plain click replaces the selection, Cmd+click adds and removes", () => {
    const one = selectTrack(state(), "a");
    const two = selectTrack(state({ ...one }), "c", { add: true });
    assert.deepEqual([...two.trackSelection].sort(), ["a", "c"]);
    const back = selectTrack(state({ ...two }), "a", { add: true });
    assert.deepEqual([...back.trackSelection], ["c"]);
    const replaced = selectTrack(state({ ...two }), "d");
    assert.deepEqual([...replaced.trackSelection], ["d"]);
  });

  test("removing the last selected track returns to all tracks", () => {
    const one = selectTrack(state(), "a");
    const gone = selectTrack(state({ ...one }), "a", { add: true });
    assert.equal(gone.trackSelection.size, 0);
    assert.equal(gone.rangeMode, "all");
  });

  test("clearing the track selection returns to all tracks", () => {
    const patch = clearTrackSelection();
    assert.equal(patch.trackSelection.size, 0);
    assert.equal(patch.rangeMode, "all");
  });
});

describe("the E switch", () => {
  test("toggles between all tracks and selected tracks only", () => {
    assert.deepEqual(toggleScopeMode(state()), { rangeMode: "selected" });
    assert.deepEqual(toggleScopeMode(state({ rangeMode: "selected" })), { rangeMode: "all" });
  });
});

describe("dimming and the chip", () => {
  test("nothing is dimmed when all tracks are affected", () => {
    assert.equal(dimmedTracks(state()).size, 0);
  });

  test("the tracks the operation will not touch are dimmed", () => {
    const lanes = dimmedTracks(state({ rangeTracks: new Set(["b"]) }));
    assert.deepEqual([...lanes].sort(), ["a", "c", "d"]);
    const picked = dimmedTracks(
      state({ rangeMode: "selected", trackSelection: new Set(["a", "b"]) }),
    );
    assert.deepEqual([...picked].sort(), ["c", "d"]);
  });

  test("no tracks selected in selected-only mode dims nothing but the chip warns", () => {
    const s = state({ rangeMode: "selected" });
    assert.equal(dimmedTracks(s).size, 0);
    assert.deepEqual(scopeChip(s), { kind: "none" });
  });

  test("the chip names the range and the tracks it will touch", () => {
    const all = scopeChip(state({ inPoint: 100, outPoint: 200 }));
    assert.deepEqual(all, { kind: "range", start: 100, end: 200, all: true, count: 4, names: [] });
    const some = scopeChip(
      state({
        inPoint: 100,
        outPoint: 200,
        rangeMode: "selected",
        trackSelection: new Set(["b", "a"]),
      }),
    );
    assert.deepEqual(some, {
      kind: "range",
      start: 100,
      end: 200,
      all: false,
      count: 2,
      names: ["Olli", "Kari"],
    });
  });

  test("without a range the chip appears only when the scope is not all tracks", () => {
    assert.equal(scopeChip(state()), null);
    const picked = scopeChip(state({ rangeMode: "selected", trackSelection: new Set(["c"]) }));
    assert.deepEqual(picked, { kind: "mode", all: false, count: 1, names: ["Music"] });
  });
});
