import assert from "node:assert/strict";
import { test } from "node:test";
import {
  eligibleBlockIds,
  othersChanging,
  overallSpan,
  overviewScale,
  overviewSpeakers,
  spansEqual,
  totalBlocks,
} from "../block-level-overview.js";

const measured = {
  rate: 10,
  threshold_db: 3,
  speakers: [
    {
      name: "A",
      track_ids: ["a"],
      blocks: [
        { id: "a0", start: 0, end: 20, gain_db: 0, deviation_db: 0 },
        { id: "a1", start: 30, end: 50, gain_db: -9, deviation_db: 9 },
      ],
    },
    {
      name: "B",
      track_ids: ["b"],
      blocks: [{ id: "b0", start: 60, end: 100, gain_db: 6, deviation_db: -8 }],
    },
  ],
};
test("one shared time and gain scale covers all speakers, including unchanged blocks", () => {
  assert.deepEqual(overviewScale(measured), { end: 100, gain: 9 });
  assert.equal(overviewSpeakers(measured)[0].rows.length, 1);
  assert.equal(overviewSpeakers(measured)[0].name, "A");
});
test("marks select whole speech blocks only, not overlapping blocks", () => {
  assert.deepEqual([...eligibleBlockIds(measured, { range: { start: 35, end: 100 } })], ["b0"]);
  assert.deepEqual(
    [...eligibleBlockIds(measured, { range: { start: 30, end: 100 }, threshold: 8.5 })],
    ["a1"],
  );
  assert.equal(eligibleBlockIds(measured, { range: { start: 0, end: 0 } }).size, 0);
});
test("threshold can only narrow measured proposals; malformed values fail closed", () => {
  assert.deepEqual([...eligibleBlockIds(measured, { threshold: 0 })], ["a1", "b0"]);
  assert.equal(eligibleBlockIds(measured, { threshold: NaN }).size, 0);
  assert.deepEqual(overviewScale({ speakers: [] }), { end: 1, gain: 1 });
});
test("others changing, the total block count and the overall span back the no-change card", () => {
  const speakers = overviewSpeakers(measured);
  const limits = { max_boost_db: 6, max_cut_db: 18 };
  const others = othersChanging(speakers, speakers[0], new Set(["b0"]), limits);
  assert.deepEqual(
    others.map((entry) => [entry.speaker.name, entry.blocks]),
    [["B", 1]],
  );
  assert.equal(othersChanging(speakers, speakers[0], new Set(["a1"]), limits).length, 0);
  assert.equal(totalBlocks(measured), 3);
  assert.deepEqual(overallSpan(measured), [-8, 9]);
  assert.equal(overallSpan({ speakers: [] }), null);
  assert.equal(spansEqual([1, 2], [1, 2]), true);
  assert.equal(spansEqual([1, 2], [1, 3]), false);
  assert.equal(spansEqual(null, null), false);
});
