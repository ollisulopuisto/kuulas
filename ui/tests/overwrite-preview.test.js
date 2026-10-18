import assert from "node:assert/strict";
import test from "node:test";
import { affectedIds, overwriteResult } from "../overwrite-preview.js";

test("overwriteResult: non-overlapping and touching clips stay unchanged, plus moved clip", () => {
  const clips = [
    { id: "c1", start: 0, length: 100 },
    { id: "c2", start: 200, length: 100 },
  ];
  // moved clip lands between c1 and c2, touching c1 at 100 and c2 at 200
  const moved = { id: "m", start: 100, length: 100 };

  const res = overwriteResult(clips, moved);
  assert.deepEqual(res, [
    { id: "c1", start: 0, length: 100 },
    { id: "m", start: 100, length: 100, moved: true },
    { id: "c2", start: 200, length: 100 },
  ]);
});

test("overwriteResult: fully covered clip is dropped", () => {
  const clips = [
    { id: "c1", start: 100, length: 50 }, // [100, 150)
    { id: "c2", start: 300, length: 100 },
  ];
  // moved covers c1 exactly
  const moved1 = { id: "m", start: 100, length: 50 };
  assert.deepEqual(overwriteResult(clips, moved1), [
    { id: "m", start: 100, length: 50, moved: true },
    { id: "c2", start: 300, length: 100 },
  ]);

  // moved covers c1 with room to spare
  const moved2 = { id: "m", start: 80, length: 100 }; // [80, 180)
  assert.deepEqual(overwriteResult(clips, moved2), [
    { id: "m", start: 80, length: 100, moved: true },
    { id: "c2", start: 300, length: 100 },
  ]);
});

test("overwriteResult: front of clip covered is trimmed at start", () => {
  const clips = [
    { id: "c1", start: 100, length: 100 }, // [100, 200)
  ];
  // moved lands at [80, 140) -> covers front of c1 up to 140
  const moved = { id: "m", start: 80, length: 60 };

  assert.deepEqual(overwriteResult(clips, moved), [
    { id: "m", start: 80, length: 60, moved: true },
    { id: "c1", start: 140, length: 60, trimmed: "start" },
  ]);
});

test("overwriteResult: end of clip covered is trimmed at end", () => {
  const clips = [
    { id: "c1", start: 100, length: 100 }, // [100, 200)
  ];
  // moved lands at [160, 250) -> covers end of c1 from 160
  const moved = { id: "m", start: 160, length: 90 };

  assert.deepEqual(overwriteResult(clips, moved), [
    { id: "c1", start: 100, length: 60, trimmed: "end" },
    { id: "m", start: 160, length: 90, moved: true },
  ]);
});

test("overwriteResult: strictly contained clip is split into left and right pieces", () => {
  const clips = [
    { id: "c1", start: 100, length: 200 }, // [100, 300)
  ];
  // moved lands inside c1: [150, 220)
  const moved = { id: "m", start: 150, length: 70 };

  assert.deepEqual(overwriteResult(clips, moved), [
    { id: "c1", start: 100, length: 50, trimmed: "end" },
    { id: "m", start: 150, length: 70, moved: true },
    { id: "c1~r", start: 220, length: 80, trimmed: "start" },
  ]);
});

test("overwriteResult: multiple clips with mixed coverage, sorted by start", () => {
  const clips = [
    { id: "c1", start: 50, length: 100 }, // [50, 150) -> end covered [120, 150)
    { id: "c2", start: 160, length: 30 }, // [160, 190) -> fully covered
    { id: "c3", start: 210, length: 100 }, // [210, 310) -> front covered [210, 250)
  ];
  // moved lands at [120, 250)
  const moved = { id: "m", start: 120, length: 130 };

  assert.deepEqual(overwriteResult(clips, moved), [
    { id: "c1", start: 50, length: 70, trimmed: "end" },
    { id: "m", start: 120, length: 130, moved: true },
    { id: "c3", start: 250, length: 60, trimmed: "start" },
  ]);
});

test("overwriteResult: moved with length <= 0 or invalid returns clips unchanged", () => {
  const clips = [{ id: "c1", start: 100, length: 100 }];
  assert.deepEqual(overwriteResult(clips, { id: "m", start: 120, length: 0 }), [
    { id: "c1", start: 100, length: 100 },
  ]);
  assert.deepEqual(overwriteResult(clips, { id: "m", start: 120, length: -50 }), [
    { id: "c1", start: 100, length: 100 },
  ]);
  assert.deepEqual(overwriteResult(clips, null), [{ id: "c1", start: 100, length: 100 }]);
  assert.deepEqual(overwriteResult(null, { id: "m", start: 100, length: 50 }), [
    { id: "m", start: 100, length: 50, moved: true },
  ]);
});

test("affectedIds: returns Set of clip IDs that are dropped, trimmed or split", () => {
  const clips = [
    { id: "c1", start: 50, length: 100 }, // [50, 150) -> end trimmed
    { id: "c2", start: 160, length: 30 }, // [160, 190) -> dropped
    { id: "c3", start: 200, length: 100 }, // [200, 300) -> split by moved [220, 260)
    { id: "c4", start: 400, length: 50 }, // untouched
  ];

  // moved [120, 180) affects c1 and c2
  const set1 = affectedIds(clips, { id: "m", start: 120, length: 60 });
  assert(set1 instanceof Set);
  assert.deepEqual([...set1].sort(), ["c1", "c2"]);

  // moved inside c3 affects c3
  const set2 = affectedIds(clips, { id: "m", start: 220, length: 40 });
  assert.deepEqual([...set2], ["c3"]);

  // non-overlapping moved affects nothing
  const set3 = affectedIds(clips, { id: "m", start: 310, length: 50 });
  assert.deepEqual([...set3], []);

  // moved touching edges affects nothing
  const setTouching = affectedIds(clips, { id: "m", start: 0, length: 50 });
  assert.deepEqual([...setTouching], []);

  // moved with length <= 0 or invalid affects nothing
  assert.deepEqual([...affectedIds(clips, { id: "m", start: 100, length: 0 })], []);
  assert.deepEqual([...affectedIds(clips, null)], []);
  assert.deepEqual([...affectedIds([], { id: "m", start: 100, length: 50 })], []);
});

test("immutability: input clips array and objects are never mutated", () => {
  const clips = [
    Object.freeze({ id: "c1", start: 50, length: 100 }),
    Object.freeze({ id: "c2", start: 200, length: 100 }),
  ];
  Object.freeze(clips);
  const moved = Object.freeze({ id: "m", start: 120, length: 100 });

  const res = overwriteResult(clips, moved);
  assert.equal(res.length, 3);
  const aff = affectedIds(clips, moved);
  assert.equal(aff.size, 2);
});
