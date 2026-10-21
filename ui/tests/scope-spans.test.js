// The in/out band and its bars are drawn only on the lanes the next range operation will
// touch, once the scope is narrowed (owner, 21.10.2026); with all tracks they run full height.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { scopeSpans } from "../range-scope.js";
import { initialState } from "../store.js";

const project = {
  tracks: [
    { id: "a", name: "Olli" },
    { id: "b", name: "Aame" },
    { id: "c", name: "Antto" },
  ],
};
const rows = [
  { kind: "bus", id: "bus", top: 0, height: 30 },
  { kind: "track", id: "a", top: 30, height: 100 },
  { kind: "track", id: "b", top: 130, height: 100 },
  { kind: "track", id: "c", top: 230, height: 100 },
];
const base = (extra = {}) => ({ ...initialState(), project, ...extra });
const opts = { rulerHeight: 40, scrollY: 0 };

describe("scopeSpans", () => {
  test("all tracks: null, the band runs the full height as before", () => {
    assert.equal(scopeSpans(base(), rows, opts), null);
  });

  test("one selected track: only its lane, in canvas coordinates", () => {
    const s = base({ trackSelection: new Set(["b"]), rangeMode: "selected" });
    assert.deepEqual(scopeSpans(s, rows, opts), [{ top: 170, height: 100 }]);
  });

  test("scrolling moves the spans", () => {
    const s = base({ trackSelection: new Set(["b"]), rangeMode: "selected" });
    assert.deepEqual(scopeSpans(s, rows, { rulerHeight: 40, scrollY: 50 }), [
      { top: 120, height: 100 },
    ]);
  });

  test("two tracks: two spans, bus rows are skipped", () => {
    const s = base({ trackSelection: new Set(["a", "c"]), rangeMode: "selected" });
    assert.deepEqual(scopeSpans(s, rows, opts), [
      { top: 70, height: 100 },
      { top: 270, height: 100 },
    ]);
  });

  test("selected mode with nothing selected touches nothing: no spans at all", () => {
    const s = base({ trackSelection: new Set(), rangeMode: "selected" });
    assert.deepEqual(scopeSpans(s, rows, opts), []);
  });

  test("lanes painted with the mouse narrow it too", () => {
    const s = base({ rangeTracks: new Set(["c"]) });
    assert.deepEqual(scopeSpans(s, rows, opts), [{ top: 270, height: 100 }]);
  });
});
