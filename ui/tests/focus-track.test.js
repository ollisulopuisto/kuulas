import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { dimmedTracks, focusTrack, scopeChip } from "../range-scope.js";
import { initialState } from "../store.js";

const project = {
  tracks: [
    { id: "a", name: "Olli" },
    { id: "b", name: "Aame" },
    { id: "c", name: "Antto" },
    { id: "d", name: "Tuukka" },
  ],
};
const base = (extra = {}) => ({ ...initialState(), project, ...extra });
const apply = (state, patch) => ({ ...state, ...patch });

describe("focusTrack: the current track and the selection are one rule", () => {
  test("clicking the second header makes it current AND the single selection; dim and chip follow", () => {
    let s = base({ focusTrack: "a", trackSelection: new Set(["a"]), rangeMode: "selected" });
    s = apply(s, focusTrack(s, "b", { mode: "select" }));
    assert.equal(s.focusTrack, "b");
    assert.deepEqual([...s.trackSelection], ["b"]);
    assert.deepEqual([...dimmedTracks(s)].sort(), ["a", "c", "d"]);
    assert.deepEqual(scopeChip(s).names, ["Aame"]);
  });

  test("clicking a clip lane (track 3) selects that track too", () => {
    let s = base();
    s = apply(s, focusTrack(s, "c", { mode: "select" }));
    assert.equal(s.focusTrack, "c");
    assert.deepEqual([...s.trackSelection], ["c"]);
    assert.equal(s.rangeMode, "selected");
  });

  test("Cmd+click adds to the selection and moves current", () => {
    let s = base({ focusTrack: "a", trackSelection: new Set(["a"]), rangeMode: "selected" });
    s = apply(s, focusTrack(s, "c", { mode: "add" }));
    assert.equal(s.focusTrack, "c");
    assert.deepEqual([...s.trackSelection].sort(), ["a", "c"]);
  });

  test("keyboard navigation with nothing selected selects nothing and dims nothing", () => {
    let s = base();
    s = apply(s, focusTrack(s, "b", { mode: "follow" }));
    assert.equal(s.focusTrack, "b");
    assert.equal(s.trackSelection.size, 0);
    assert.equal(s.rangeMode, "all");
    assert.equal(dimmedTracks(s).size, 0);
  });

  test("keyboard navigation with a selection moves the selection along", () => {
    let s = base({ focusTrack: "a", trackSelection: new Set(["a"]), rangeMode: "selected" });
    s = apply(s, focusTrack(s, "b", { mode: "follow" }));
    assert.deepEqual([...s.trackSelection], ["b"]);
    assert.equal(s.rangeMode, "selected");
  });

  test("a fresh or reloaded project is not pinned to the first track", () => {
    const s = base();
    assert.equal(s.trackSelection.size, 0);
    assert.equal(s.rangeMode, "all");
    assert.equal(dimmedTracks(s).size, 0);
    assert.equal(scopeChip(s), null);
  });
});
