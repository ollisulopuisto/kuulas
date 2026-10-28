import assert from "node:assert/strict";
import { test } from "node:test";
import { bindDialRange, controlLines } from "../dial-range.js";

test("height tiers keep controls at each transition", () => {
  for (const [height, expected] of [
    [24, 1],
    [40, 1],
    [59, 1],
    [60, 2],
    [80, 2],
    [99, 2],
    [100, 3],
    [200, 3],
  ])
    assert.equal(controlLines(height), expected);
});
test("dial indicator maps ends and centre to a 270-degree sweep", () => {
  const styles = new Map();
  const attributes = new Map([["aria-label", "Pan"]]);
  const input = {
    min: -100,
    max: 100,
    value: 0,
    parentElement: { style: { setProperty: (k, v) => styles.set(k, v) } },
    addEventListener() {},
    setAttribute: (k, v) => attributes.set(k, v),
    getAttribute: (k) => attributes.get(k),
  };
  const paint = bindDialRange(input, () => true);
  for (const [value, angle] of [
    [-100, "-135deg"],
    [0, "0deg"],
    [100, "135deg"],
  ]) {
    input.value = value;
    paint();
    assert.equal(styles.get("--dial-angle"), angle);
  }
  assert.equal(attributes.get("aria-orientation"), "vertical");
});
