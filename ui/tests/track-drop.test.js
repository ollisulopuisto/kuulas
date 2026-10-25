import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { dropIndex } from "../track-drop.js";

// Three other headers, each 40 px tall, from y = 0: midpoints 20, 60, 100.
const mids = [20, 60, 100];

describe("where a dragged track header lands", () => {
  test("above every other header is first", () => {
    assert.equal(dropIndex(mids, 5), 0);
  });
  test("between headers counts the midpoints above the pointer", () => {
    assert.equal(dropIndex(mids, 70), 2);
  });
  test("below every other header is last", () => {
    assert.equal(dropIndex(mids, 500), 3);
  });
});
