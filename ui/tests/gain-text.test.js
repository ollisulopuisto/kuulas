import assert from "node:assert/strict";
import test from "node:test";
import { gainSteps, levelBadge } from "../gain-text.js";

test("levelBadge: 0 or negative values return empty string", () => {
  assert.equal(levelBadge(0), "");
  assert.equal(levelBadge(-0), "");
  assert.equal(levelBadge(-0.1), "");
  assert.equal(levelBadge(-12), "");
});

test("levelBadge: non-finite or non-numeric values return empty string", () => {
  assert.equal(levelBadge(Number.NaN), "");
  assert.equal(levelBadge(Number.POSITIVE_INFINITY), "");
  assert.equal(levelBadge(Number.NEGATIVE_INFINITY), "");
  assert.equal(levelBadge(null), "");
  assert.equal(levelBadge(undefined), "");
  assert.equal(levelBadge("0.5"), "");
});

test("levelBadge: values in (0, 99.9] formatted with leading plus and one decimal", () => {
  assert.equal(levelBadge(0.3), "+0.3");
  assert.equal(levelBadge(0.1), "+0.1");
  assert.equal(levelBadge(2.14), "+2.1");
  assert.equal(levelBadge(2.16), "+2.2");
  assert.equal(levelBadge(12), "+12.0");
  assert.equal(levelBadge(99.9), "+99.9");
});

test("levelBadge: values above 99.9 capped at +99.9", () => {
  assert.equal(levelBadge(100), "+99.9");
  assert.equal(levelBadge(99.95), "+99.9");
  assert.equal(levelBadge(150.2), "+99.9");
});

test("gainSteps: normal step (0.5 dB) up and down", () => {
  assert.equal(gainSteps(0, 1), 0.5);
  assert.equal(gainSteps(0.5, 1), 1.0);
  assert.equal(gainSteps(0, -1), -0.5);
  assert.equal(gainSteps(-0.5, -1), -1.0);
  assert.equal(gainSteps(3.2, 1), 3.7);
  assert.equal(gainSteps(3.2, -1), 2.7);
});

test("gainSteps: fine step (0.1 dB) up and down", () => {
  assert.equal(gainSteps(0, 1, true), 0.1);
  assert.equal(gainSteps(0.1, 1, true), 0.2);
  assert.equal(gainSteps(0, -1, true), -0.1);
  assert.equal(gainSteps(-0.1, -1, true), -0.2);
  assert.equal(gainSteps(3.2, 1, true), 3.3);
  assert.equal(gainSteps(3.2, -1, true), 3.1);
});

test("gainSteps: direction 0 returns clamped value rounded to one decimal", () => {
  assert.equal(gainSteps(0, 0), 0);
  assert.equal(gainSteps(3.24, 0), 3.2);
  assert.equal(gainSteps(3.26, 0), 3.3);
  assert.equal(gainSteps(15, 0), 12);
  assert.equal(gainSteps(-70, 0), -60);
});

test("gainSteps: non-finite db counts as 0", () => {
  assert.equal(gainSteps(Number.NaN, 1), 0.5);
  assert.equal(gainSteps(null, 1), 0.5);
  assert.equal(gainSteps(undefined, -1), -0.5);
  assert.equal(gainSteps(Number.POSITIVE_INFINITY, 0), 0);
  assert.equal(gainSteps(Number.NaN, 1, true), 0.1);
  assert.equal(gainSteps(Number.NaN, 0), 0);
});

test("gainSteps: clamped to upper bound of 12 dB", () => {
  assert.equal(gainSteps(12, 1), 12);
  assert.equal(gainSteps(11.8, 1), 12);
  assert.equal(gainSteps(11.95, 1, true), 12);
  assert.equal(gainSteps(20, 1), 12);
});

test("gainSteps: clamped to lower bound of -60 dB", () => {
  assert.equal(gainSteps(-60, -1), -60);
  assert.equal(gainSteps(-59.8, -1), -60);
  assert.equal(gainSteps(-59.95, -1, true), -60);
  assert.equal(gainSteps(-80, -1), -60);
});

test("gainSteps: prevents negative zero (-0)", () => {
  const res = gainSteps(-0.5, 1);
  assert.equal(res, 0);
  assert.equal(Object.is(res, -0), false);
  assert.equal(Object.is(res, 0), true);

  const resFine = gainSteps(-0.1, 1, true);
  assert.equal(resFine, 0);
  assert.equal(Object.is(resFine, 0), true);
});
