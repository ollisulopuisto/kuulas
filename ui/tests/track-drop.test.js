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

test("visible rows translate to project indices without displacing folded tracks", async () => {
  const { trackDropIndex } = await import("../track-drop.js");
  const order = ["hidden-1", "hidden-2", "a", "b"];
  const visible = [
    { id: "b", midpoint: 200 },
    { id: "a", midpoint: 100 },
  ];
  assert.equal(trackDropIndex(order, "a", visible, 300), 3);
  assert.equal(trackDropIndex(order, "b", visible, 50), 2);
  assert.equal(trackDropIndex(order, "b", [], 50), 3);
});

test("a folded bus row stands in for its first member", async () => {
  const { trackDropIndex } = await import("../track-drop.js");
  const order = ["a", "hidden-1", "hidden-2", "b"];
  const visible = [
    // The caller maps the folded bus header to its first member.
    { id: "hidden-1", midpoint: 150 },
    { id: "b", midpoint: 250 },
  ];
  // A stationary click stays put instead of jumping the hidden members.
  assert.equal(trackDropIndex(order, "a", visible, 100), 0);
  assert.equal(trackDropIndex(order, "a", visible, 200), 2);
});
