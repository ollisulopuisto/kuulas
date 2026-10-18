import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { parseDbText, parsePanText } from "../value-edit.js";

describe("typing a gain value", () => {
  test("accepts a dot or comma decimal, a minus or the typographic minus, and an optional dB", () => {
    assert.equal(parseDbText("-2.4"), -2.4);
    assert.equal(parseDbText("−2,4 dB"), -2.4);
    assert.equal(parseDbText("  3 db "), 3);
    assert.equal(parseDbText("+1,5"), 1.5);
    assert.equal(parseDbText("0"), 0);
  });
  test("clamps to the slider's range", () => {
    assert.equal(parseDbText("99", { min: -60, max: 12 }), 12);
    assert.equal(parseDbText("-100", { min: -60, max: 12 }), -60);
  });
  test("rounds to one decimal, the slider's step", () => {
    assert.equal(parseDbText("-2.449"), -2.4);
  });
  test("anything else is null (the old value stays)", () => {
    for (const text of ["", "abc", "1,2,3", "--3", "12 dBm x"]) {
      assert.equal(parseDbText(text), null, text);
    }
  });
});

describe("typing a pan value", () => {
  test("L and R with a number, either order, any case, and C for centre", () => {
    assert.equal(parsePanText("L 30"), -0.3);
    assert.equal(parsePanText("30 R"), 0.3);
    assert.equal(parsePanText("r20"), 0.2);
    assert.equal(parsePanText("C"), 0);
    assert.equal(parsePanText("keski"), 0);
    assert.equal(parsePanText("v 10"), -0.1); // Finnish V(asen) and O(ikea)
    assert.equal(parsePanText("o 10"), 0.1);
  });
  test("a bare number is a percentage: negative left, positive right", () => {
    assert.equal(parsePanText("-30"), -0.3);
    assert.equal(parsePanText("30"), 0.3);
    assert.equal(parsePanText("0"), 0);
  });
  test("clamps to the full width and rounds to whole percent", () => {
    assert.equal(parsePanText("L 250"), -1);
    assert.equal(parsePanText("R 33,6"), 0.34);
  });
  test("anything else is null", () => {
    for (const text of ["", "left", "L", "L x", "12 34"]) {
      assert.equal(parsePanText(text), null, text);
    }
  });
});
