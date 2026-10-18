import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { CLIP_LIMIT_DB, columnOvers, maxOverDb, overLabel, overs } from "../clip-overs.js";

// The same cases tests/test_gain_overs_fixture.py reads: this must match clip_overs.py.
const cases = JSON.parse(
  readFileSync(fileURLToPath(new URL("./fixtures/gain-overs-cases.json", import.meta.url)), "utf8"),
);

describe("clip overs agree with clip_overs.py", () => {
  for (const c of cases.overs) {
    test(`overs ${JSON.stringify(c.peaks)} at ${c.gain} dB`, () => {
      assert.deepEqual(overs(c.peaks, c.gain, c.limit), c.result);
    });
  }
  for (const c of cases.max_over) {
    test(`max over ${JSON.stringify(c.peaks)} at ${c.gain} dB`, () => {
      assert.ok(Math.abs(maxOverDb(c.peaks, c.gain) - c.result) < 1e-3);
    });
  }
});

describe("clip overs edge cases", () => {
  test("the limit is -0.1 dBFS (a future setting)", () => {
    assert.equal(CLIP_LIMIT_DB, -0.1);
  });
  test("a positive limit and a non-finite gain are refused", () => {
    assert.throws(() => overs([], 0, 1));
    assert.throws(() => overs([], Number.NaN));
    assert.throws(() => maxOverDb([], Number.POSITIVE_INFINITY));
  });
});

describe("overLabel", () => {
  const t = (key, values = {}) => `${key}${values.db === undefined ? "" : `:${values.db}`}`;
  const format = (value) => value.toFixed(1);
  test("says how far over full scale", () => {
    assert.equal(overLabel(2.14, t, format), "ui.clip.over:2.1");
  });
  test("between the limit and full scale it says it is at the limit", () => {
    assert.equal(overLabel(0, t, format), "ui.clip.at_limit");
  });
});

describe("columnOvers (per drawn column, gain varies by column)", () => {
  test("flags only the columns whose peak after their own gain passes the limit", () => {
    const data = Float32Array.of(-0.5, 0.5, -0.5, 0.5, -0.5, 0.5);
    const db = Float32Array.of(0, 6.5, 5.5);
    const { over, maxOver } = columnOvers(data, db);
    assert.deepEqual([...over], [0, 1, 0]);
    assert.ok(Math.abs(maxOver - 20 * Math.log10(0.5 * 10 ** (6.5 / 20))) < 1e-6);
  });
  test("nothing over gives 0 dB over and no flags", () => {
    const { over, maxOver } = columnOvers(Float32Array.of(-0.1, 0.1), Float32Array.of(0));
    assert.deepEqual([...over], [0]);
    assert.equal(maxOver, 0);
  });
  test("between the limit and full scale is over, but 0 dB above full scale", () => {
    const { over, maxOver } = columnOvers(Float32Array.of(0, 0.995), Float32Array.of(0));
    assert.deepEqual([...over], [1]);
    assert.equal(maxOver, 0);
  });
  test("-inf gain is silence", () => {
    const { over } = columnOvers(Float32Array.of(-1, 1), Float32Array.of(Number.NEGATIVE_INFINITY));
    assert.deepEqual([...over], [0]);
  });
});
