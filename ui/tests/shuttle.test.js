import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { chipSpeed, heldScrubSpeed, press, STEP_MS, scrubStyle } from "../shuttle.js";

// The same cases tests/test_shuttle.py reads: the JS ladder must match shuttle.py.
const cases = JSON.parse(
  readFileSync(fileURLToPath(new URL("./fixtures/shuttle-cases.json", import.meta.url)), "utf8"),
);

describe("the shuttle ladder agrees with shuttle.py", () => {
  for (const c of cases.press) {
    test(`${c.speed} then ${c.key} gives ${c.result}`, () => {
      assert.equal(press(c.speed, c.key) + 0, c.result);
    });
  }
  for (const c of cases.scrub_style) {
    test(`scrub style at ${c.speed}`, () => assert.equal(scrubStyle(c.speed), c.style));
  }
  for (const c of cases.held) {
    test(`held scrub ${c.direction}`, () => assert.equal(heldScrubSpeed(c.direction), c.speed));
  }
  test("an unknown key is refused", () => assert.throws(() => press(1, "x")));
  test("the step is 10 ms", () => assert.equal(STEP_MS, 10));
});

describe("the speed chip", () => {
  const format = (v, { digits }) => v.toFixed(digits).replace("-", "−");
  test("hidden at 1x and while stopped", () => {
    assert.equal(chipSpeed(1, true, format), null);
    assert.equal(chipSpeed(2, false, format), null);
  });
  test("shows forward, backward and fractional speeds", () => {
    assert.equal(chipSpeed(2, true, format), "2");
    assert.equal(chipSpeed(-1.5, true, format), "−1.5");
    assert.equal(chipSpeed(-1, true, format), "−1");
  });
});
