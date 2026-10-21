import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { etaLabel, etaVisible } from "../eta-label.js";

describe("etaLabel", () => {
  test("returns key and params for valid shapes", () => {
    assert.deepEqual(etaLabel(["under_minute", 0]), {
      key: "ui.eta.under_minute",
      params: {},
    });
    assert.deepEqual(etaLabel(["minutes", 1]), {
      key: "ui.eta.minutes",
      params: { n: 1 },
    });
    assert.deepEqual(etaLabel(["minutes", 45]), {
      key: "ui.eta.minutes",
      params: { n: 45 },
    });
    assert.deepEqual(etaLabel(["hours_minutes", [1, 20]]), {
      key: "ui.eta.hours_minutes",
      params: { h: 1, m: 20 },
    });
    assert.deepEqual(etaLabel(["hours_minutes", [0, 59]]), {
      key: "ui.eta.hours_minutes",
      params: { h: 0, m: 59 },
    });
  });

  test("returns null for null or missing input", () => {
    assert.equal(etaLabel(null), null);
    assert.equal(etaLabel(undefined), null);
    assert.equal(etaLabel(), null);
  });

  test("returns null for non-array or wrong arity input", () => {
    assert.equal(etaLabel("under_minute"), null);
    assert.equal(etaLabel(123), null);
    assert.equal(etaLabel({}), null);
    assert.equal(etaLabel([]), null);
    assert.equal(etaLabel(["under_minute"]), null);
    assert.equal(etaLabel(["under_minute", 0, 1]), null);
    assert.equal(etaLabel(["minutes"]), null);
    assert.equal(etaLabel(["minutes", 5, 10]), null);
    assert.equal(etaLabel(["hours_minutes"]), null);
    assert.equal(etaLabel(["hours_minutes", [1]]), null);
    assert.equal(etaLabel(["hours_minutes", [1, 2, 3]]), null);
    assert.equal(etaLabel(["hours_minutes", "1h 20m"]), null);
  });

  test("returns null for negative numbers, non-numbers, or non-finite values", () => {
    assert.equal(etaLabel(["under_minute", -1]), null);
    assert.equal(etaLabel(["under_minute", "0"]), null);
    assert.equal(etaLabel(["minutes", -5]), null);
    assert.equal(etaLabel(["minutes", "12"]), null);
    assert.equal(etaLabel(["minutes", Number.NaN]), null);
    assert.equal(etaLabel(["minutes", Number.POSITIVE_INFINITY]), null);
    assert.equal(etaLabel(["hours_minutes", [-1, 20]]), null);
    assert.equal(etaLabel(["hours_minutes", [1, -5]]), null);
    assert.equal(etaLabel(["hours_minutes", ["1", 20]]), null);
    assert.equal(etaLabel(["hours_minutes", [1, "20"]]), null);
    assert.equal(etaLabel(["hours_minutes", [Number.NaN, 20]]), null);
    assert.equal(etaLabel(["hours_minutes", [1, Number.POSITIVE_INFINITY]]), null);
  });

  test("returns null for unknown kind", () => {
    assert.equal(etaLabel(["seconds", 30]), null);
    assert.equal(etaLabel(["hours", 2]), null);
    assert.equal(etaLabel(["unknown", 0]), null);
  });

  test("does not mutate input", () => {
    const parts = Object.freeze(["hours_minutes", Object.freeze([2, 15])]);
    const res = etaLabel(parts);
    assert.deepEqual(res, {
      key: "ui.eta.hours_minutes",
      params: { h: 2, m: 15 },
    });
  });
});

describe("etaVisible", () => {
  test("visibility rule at standard boundary values", () => {
    assert.equal(etaVisible(0), false);
    assert.equal(etaVisible(4.9), false);
    assert.equal(etaVisible(5), true);
    assert.equal(etaVisible(50), true);
    assert.equal(etaVisible(99.9), true);
    assert.equal(etaVisible(100), false);
  });

  test("returns false for values outside 0..100 or non-finite values", () => {
    assert.equal(etaVisible(-1), false);
    assert.equal(etaVisible(101), false);
    assert.equal(etaVisible(Number.NaN), false);
    assert.equal(etaVisible(Number.POSITIVE_INFINITY), false);
    assert.equal(etaVisible(Number.NEGATIVE_INFINITY), false);
    assert.equal(etaVisible(null), false);
    assert.equal(etaVisible(undefined), false);
    assert.equal(etaVisible("50"), false);
  });

  test("respects custom minPercent", () => {
    assert.equal(etaVisible(9.9, 10), false);
    assert.equal(etaVisible(10, 10), true);
    assert.equal(etaVisible(2, 1), true);
    assert.equal(etaVisible(0.5, 1), false);
  });
});
