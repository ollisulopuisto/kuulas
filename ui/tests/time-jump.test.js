import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveTime } from "../time-jump.js";

const RATE = 48_000;
const at = (text, from = 10 * RATE, end = 600 * RATE) =>
  resolveTime(text, { from, end, rate: RATE });

describe("resolveTime absolute", () => {
  it("reads seconds and m:ss, dot or comma", () => {
    assert.equal(at("83,2"), Math.round(83.2 * RATE));
    assert.equal(at("1:23.5"), Math.round(83.5 * RATE));
    assert.equal(at("0"), 0);
  });
  it("clamps to the end", () => {
    assert.equal(at("9999"), 600 * RATE);
  });
});

describe("resolveTime relative", () => {
  it("adds and subtracts seconds from the current frame", () => {
    assert.equal(at("+100"), 110 * RATE);
    assert.equal(at("-5"), 5 * RATE);
    assert.equal(at("+1:30"), 100 * RATE);
    assert.equal(at("+ 2,5"), Math.round(12.5 * RATE));
  });
  it("takes a Unicode minus", () => {
    assert.equal(at("−5"), 5 * RATE);
  });
  it("clamps at 0 and at the end", () => {
    assert.equal(at("-30"), 0);
    assert.equal(at("+100000"), 600 * RATE);
  });
  it("allows an ms suffix", () => {
    assert.equal(at("+500ms"), 10 * RATE + 24_000);
    assert.equal(at("-250 ms"), 10 * RATE - 12_000);
    assert.equal(at("500ms"), 24_000);
  });
});

describe("resolveTime invalid", () => {
  it("returns null so the value is left alone", () => {
    for (const bad of [
      "",
      "  ",
      "abc",
      "+",
      "-",
      "++5",
      "1:60",
      "5x",
      "ms",
      "1:30ms",
      null,
      undefined,
    ]) {
      assert.equal(at(bad), null, String(bad));
    }
  });
});
