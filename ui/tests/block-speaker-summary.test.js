import assert from "node:assert/strict";
import { test } from "node:test";
import { speakerSummary } from "../block-level-overview.js";

const speaker = {
  blocks: [
    { id: "a", deviation_db: -12, gain_db: 6 },
    { id: "b", deviation_db: 22, gain_db: -18 },
    { id: "c", deviation_db: 2, gain_db: 0 },
    { id: "d", deviation_db: -4, gain_db: 4 },
  ],
};
const limits = { max_boost_db: 6, max_cut_db: 18 };
test("speaker estimates use own reference as zero and actual proposal caps", () => {
  assert.deepEqual(speakerSummary(speaker, new Set(["a", "b", "d"]), limits), {
    before: [-12, 22],
    after: [-6, 4],
    blocks: 3,
    lift: 6,
    cut: 18,
    limited: 2,
    leftOut: 1,
  });
});
test("unchecked and filtered proposals stay at measured level in after estimate", () => {
  assert.deepEqual(speakerSummary(speaker, new Set(["d"]), limits), {
    before: [-12, 22],
    after: [-12, 22],
    blocks: 1,
    lift: 4,
    cut: 0,
    limited: 0,
    leftOut: 3,
  });
});
test("empty and non-finite measurements do not claim a level spread", () => {
  const summary = speakerSummary(
    { blocks: [{ id: "bad", deviation_db: NaN, gain_db: 6 }] },
    new Set(),
    limits,
  );
  assert.equal(summary.before, null);
  assert.equal(summary.after, null);
  assert.equal(summary.blocks, 0);
});

test("long recordings do not spread block arrays into function arguments", () => {
  const blocks = Array.from({ length: 200000 }, (_, i) => ({
    id: String(i),
    deviation_db: i % 2 ? 22 : -12,
    gain_db: i % 2 ? -18 : 6,
  }));
  const summary = speakerSummary({ blocks }, new Set(blocks.map((row) => row.id)), limits);
  assert.deepEqual(summary.before, [-12, 22]);
  assert.deepEqual(summary.after, [-6, 4]);
  assert.equal(summary.blocks, 200000);
  assert.equal(summary.lift, 6);
  assert.equal(summary.cut, 18);
});
