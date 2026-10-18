import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { escapeAction } from "../escape.js";

describe("what Esc does", () => {
  test("leaves a text field first, whatever is selected", () => {
    assert.equal(escapeAction({ inTextField: true, selection: new Set(["a"]) }), "blur");
  });
  test("clears the clip selection", () => {
    assert.equal(escapeAction({ inTextField: false, selection: new Set(["a"]) }), "clear");
  });
  test("clears the in and out marks too, even with nothing selected (owner, 2026-10-18)", () => {
    assert.equal(escapeAction({ inTextField: false, inPoint: 10 }), "clear");
    assert.equal(escapeAction({ inTextField: false, outPoint: 99 }), "clear");
    assert.equal(escapeAction({ inTextField: false, inPoint: null, outPoint: null }), "home");
  });
  test("clears the lanes a dragged range covered", () => {
    assert.equal(
      escapeAction({ inTextField: false, selection: new Set(), rangeTracks: new Set(["t"]) }),
      "clear",
    );
  });
  test("with nothing selected it goes home (the timeline gets focus)", () => {
    assert.equal(escapeAction({ inTextField: false, selection: new Set() }), "home");
    assert.equal(escapeAction({ inTextField: false }), "home");
  });
});
