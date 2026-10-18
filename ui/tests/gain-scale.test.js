import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { columnGainsDb, envelopeDbAt, totalGainDb, waveformScale } from "../gain-scale.js";

// The same cases tests/test_gain_overs_fixture.py reads: this must match gain_scale.py.
const cases = JSON.parse(
  readFileSync(fileURLToPath(new URL("./fixtures/gain-overs-cases.json", import.meta.url)), "utf8"),
);
const num = (value) =>
  typeof value === "string" ? Number(value.replace("inf", "Infinity")) : value;
const near = (got, want) => {
  if (!Number.isFinite(want)) assert.equal(got, want);
  else assert.ok(Math.abs(got - want) < 1e-9, `${got} vs ${want}`);
};

describe("gain scale agrees with gain_scale.py", () => {
  for (const c of cases.total) {
    test(`total ${JSON.stringify(c.args)}`, () => {
      near(totalGainDb(...c.args.map(num)), num(c.result));
    });
  }
  for (const c of cases.scale) {
    test(`scale ${c.db} dB`, () => {
      near(waveformScale(num(c.db), c.max), c.result);
    });
  }
  for (const c of cases.envelope) {
    test(`envelope ${JSON.stringify(c.points)} at ${c.frame}`, () => {
      near(envelopeDbAt(c.points, c.frame), c.result);
    });
  }
});

describe("gain scale edge cases", () => {
  test("nan and +inf are refused", () => {
    assert.throws(() => totalGainDb(Number.NaN, 0));
    assert.throws(() => totalGainDb(0, Number.POSITIVE_INFINITY));
  });
  test("an envelope is not mutated", () => {
    const points = [
      [200, 6],
      [100, -6],
    ];
    const before = JSON.stringify(points);
    envelopeDbAt(points, 150);
    assert.equal(JSON.stringify(points), before);
  });
});

describe("per-column gain", () => {
  test("no envelope: every column gets the base gain", () => {
    assert.deepEqual([...columnGainsDb(3, [], 0, 256, 4)], [3, 3, 3, 3]);
  });
  test("an envelope is read at each column's centre in source frames", () => {
    const db = columnGainsDb(
      0,
      [
        [0, 0],
        [1000, 10],
      ],
      0,
      100,
      3,
    );
    near(db[0], 0.5);
    near(db[1], 1.5);
    near(db[2], 2.5);
  });
  test("the clip's offset moves the envelope window", () => {
    const db = columnGainsDb(
      2,
      [
        [0, 0],
        [1000, 10],
      ],
      500,
      100,
      1,
    );
    near(db[0], 2 + 5.5);
  });
});
