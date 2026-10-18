import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { escapeAction } from "../escape.js";

describe("what Esc does", () => {
  test("leaves a text field first, whatever is selected", () => {
    assert.equal(escapeAction({ inTextField: true, selection: new Set(["a"]) }), "blur");
  });
  test("clears the clip selection, keeping the in and out marks", () => {
    assert.equal(escapeAction({ inTextField: false, selection: new Set(["a"]) }), "clear");
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
