import assert from "node:assert/strict";
import test from "node:test";
import { overlappedIds, overlapsOf, topClipAt } from "../clip-overlaps.js";

test("overlapsOf: non-overlapping separated clips return empty array", () => {
  const clips = [
    { id: "c1", start: 0, length: 100 },
    { id: "c2", start: 150, length: 50 },
    { id: "c3", start: 300, length: 200 },
  ];
  assert.deepEqual(overlapsOf(clips), []);
});

test("overlapsOf: touching adjacent clips (end === start) do not overlap", () => {
  const clips = [
    { id: "c1", start: 0, length: 100 },
    { id: "c2", start: 100, length: 50 },
    { id: "c3", start: 150, length: 50 },
  ];
  assert.deepEqual(overlapsOf(clips), []);
});

test("overlapsOf: partial overlap returns a, b, start, end with a starting first", () => {
  const clips = [
    { id: "c1", start: 0, length: 100 },
    { id: "c2", start: 80, length: 50 },
  ];
  // c1 span: [0, 100), c2 span: [80, 130). Overlap: [80, 100).
  assert.deepEqual(overlapsOf(clips), [{ a: "c1", b: "c2", start: 80, end: 100 }]);

  // Order in input inverted: a is still the one that starts first
  const inverted = [
    { id: "c2", start: 80, length: 50 },
    { id: "c1", start: 0, length: 100 },
  ];
  assert.deepEqual(overlapsOf(inverted), [{ a: "c1", b: "c2", start: 80, end: 100 }]);
});

test("overlapsOf: equal start times breaks tie by earlier in input", () => {
  const clips = [
    { id: "c1", start: 100, length: 200 },
    { id: "c2", start: 100, length: 150 },
  ];
  // c1 is earlier in input, so a is c1, b is c2
  assert.deepEqual(overlapsOf(clips), [{ a: "c1", b: "c2", start: 100, end: 250 }]);

  const reversed = [
    { id: "c2", start: 100, length: 150 },
    { id: "c1", start: 100, length: 200 },
  ];
  // c2 is earlier in input, so a is c2, b is c1
  assert.deepEqual(overlapsOf(reversed), [{ a: "c2", b: "c1", start: 100, end: 250 }]);
});

test("overlapsOf: complete containment (short clip inside long clip)", () => {
  const clips = [
    { id: "c1", start: 50, length: 500 },
    { id: "c2", start: 100, length: 50 },
  ];
  assert.deepEqual(overlapsOf(clips), [{ a: "c1", b: "c2", start: 100, end: 150 }]);
});

test("overlapsOf: multiple overlaps sorted by start then end", () => {
  const clips = [
    { id: "c3", start: 200, length: 100 }, // [200, 300)
    { id: "c1", start: 0, length: 150 }, // [0, 150)
    { id: "c2", start: 100, length: 120 }, // [100, 220)
  ];
  // Overlap c1 and c2: [100, 150)
  // Overlap c2 and c3: [200, 220)
  assert.deepEqual(overlapsOf(clips), [
    { a: "c1", b: "c2", start: 100, end: 150 },
    { a: "c2", b: "c3", start: 200, end: 220 },
  ]);

  // Multiple overlaps with same start sorted by end
  const clips2 = [
    { id: "c1", start: 0, length: 300 }, // [0, 300)
    { id: "c2", start: 100, length: 50 }, // [100, 150) -> overlap [100, 150)
    { id: "c3", start: 100, length: 100 }, // [100, 200) -> overlap [100, 200)
  ];
  // Between c1 and c2: [100, 150)
  // Between c1 and c3: [100, 200)
  // Between c2 and c3: [100, 150)
  const result = overlapsOf(clips2);
  assert.equal(result.length, 3);
  assert.equal(result[0].start, 100);
  assert.equal(result[1].start, 100);
  assert.equal(result[2].start, 100);
  assert.deepEqual(
    result.map((o) => o.end),
    [150, 150, 200],
  );
});

test("overlapsOf: clips with length <= 0 or invalid clips are ignored", () => {
  const clips = [
    { id: "c1", start: 100, length: 0 },
    { id: "c2", start: 100, length: -50 },
    { id: "c3", start: 50, length: 200 },
    { id: "c4", start: 120, length: 50 },
    null,
    { id: "c5", start: 130 },
  ];
  // Only c3 and c4 are valid. Overlap: [120, 170).
  assert.deepEqual(overlapsOf(clips), [{ a: "c3", b: "c4", start: 120, end: 170 }]);
  assert.deepEqual(overlapsOf([]), []);
  assert.deepEqual(overlapsOf(null), []);
  assert.deepEqual(overlapsOf(undefined), []);
});

test("overlappedIds: returns a Set of ids that overlap any other clip", () => {
  const clips = [
    { id: "c1", start: 0, length: 100 }, // overlaps c2
    { id: "c2", start: 80, length: 50 }, // overlaps c1
    { id: "c3", start: 200, length: 50 }, // clear
    { id: "c4", start: 400, length: 100 }, // overlaps c5
    { id: "c5", start: 450, length: 100 }, // overlaps c4
  ];

  const ids = overlappedIds(clips);
  assert(ids instanceof Set);
  assert.deepEqual([...ids].sort(), ["c1", "c2", "c4", "c5"]);

  // No overlaps
  assert.deepEqual(
    overlappedIds([
      { id: "c1", start: 0, length: 50 },
      { id: "c2", start: 60, length: 50 },
    ]),
    new Set(),
  );

  // Empty or invalid input
  assert.deepEqual(overlappedIds([]), new Set());
  assert.deepEqual(overlappedIds(null), new Set());
});

test("topClipAt: frame outside any clip returns null", () => {
  const clips = [
    { id: "c1", start: 100, length: 50 },
    { id: "c2", start: 200, length: 50 },
  ];
  assert.equal(topClipAt(clips, 50), null);
  assert.equal(topClipAt(clips, 175), null);
  assert.equal(topClipAt(clips, 300), null);
  assert.equal(topClipAt([], 100), null);
  assert.equal(topClipAt(null, 100), null);
  assert.equal(topClipAt(clips, Number.NaN), null);
  assert.equal(topClipAt(clips, Number.POSITIVE_INFINITY), null);
});

test("topClipAt: boundary test (start inclusive, end exclusive)", () => {
  const clips = [{ id: "c1", start: 100, length: 50 }];
  assert.equal(topClipAt(clips, 100), "c1"); // start inclusive
  assert.equal(topClipAt(clips, 125), "c1");
  assert.equal(topClipAt(clips, 149), "c1");
  assert.equal(topClipAt(clips, 150), null); // end exclusive
  assert.equal(topClipAt(clips, 99), null);
});

test("topClipAt: among overlapping clips holding frame, shorter one wins", () => {
  const clips = [
    { id: "long", start: 0, length: 1000 },
    { id: "medium", start: 200, length: 300 },
    { id: "short", start: 300, length: 50 },
  ];
  // At frame 100: only long exists
  assert.equal(topClipAt(clips, 100), "long");
  // At frame 250: long and medium hold frame -> medium wins (300 < 1000)
  assert.equal(topClipAt(clips, 250), "medium");
  // At frame 320: long, medium, short all hold frame -> short wins (50 < 300 < 1000)
  assert.equal(topClipAt(clips, 320), "short");
  // At frame 360: long and medium hold frame (short ended at 350) -> medium wins
  assert.equal(topClipAt(clips, 360), "medium");
});

test("topClipAt: ties in length go to the later clip in the list", () => {
  const clips = [
    { id: "first", start: 100, length: 100 },
    { id: "second", start: 120, length: 100 },
  ];
  // At frame 150: both hold frame, both have length 100. Later clip ("second") wins.
  assert.equal(topClipAt(clips, 150), "second");

  // Inverted input order
  const inverted = [
    { id: "second", start: 120, length: 100 },
    { id: "first", start: 100, length: 100 },
  ];
  // Later clip is now "first"
  assert.equal(topClipAt(inverted, 150), "first");
});

test("topClipAt: clips with length <= 0 are ignored", () => {
  const clips = [
    { id: "c0", start: 100, length: 0 },
    { id: "cneg", start: 80, length: -20 },
    { id: "c1", start: 50, length: 100 },
  ];
  assert.equal(topClipAt(clips, 100), "c1");
});

test("immutability: input clips array and clip objects are never mutated", () => {
  const clips = [
    Object.freeze({ id: "c1", start: 100, length: 100 }),
    Object.freeze({ id: "c2", start: 50, length: 80 }),
    Object.freeze({ id: "c3", start: 120, length: 100 }),
  ];
  Object.freeze(clips);

  // Calling all functions on frozen data
  const overlaps = overlapsOf(clips);
  assert.equal(overlaps.length, 3);

  const ids = overlappedIds(clips);
  assert.equal(ids.size, 3);

  const top = topClipAt(clips, 130);
  assert.equal(top, "c3");
});
