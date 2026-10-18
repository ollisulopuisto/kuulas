import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { dbText, labelFor, peakOf, scaleFactor } from "../waveform-scale.js";

describe("peakOf", () => {
  test("empty array returns 0", () => {
    assert.equal(peakOf([]), 0);
    assert.equal(peakOf(null), 0);
  });

  test("all-zero array returns 0", () => {
    assert.equal(peakOf([0, 0, 0, 0]), 0);
  });

  test("percentile on a known array", () => {
    // 100 values: 0.01, 0.02, ..., 1.00
    const values = Array.from({ length: 100 }, (_, i) => (i + 1) / 100);
    assert.equal(peakOf(values, 0.5), 0.5);
    assert.equal(peakOf(values, 0.9), 0.9);
    assert.equal(peakOf(values, 0.99), 0.99);
  });

  test("a single loud click ignored by the 0.99 percentile", () => {
    // 99 values of 0.2 and 1 loud click of 1.0 (100 values total)
    const values = Array.from({ length: 99 }, () => 0.2).concat([1.0]);
    // 99th item (index 98) out of 100 is 0.2
    assert.equal(peakOf(values, 0.99), 0.2);
  });
});

describe("scaleFactor", () => {
  test("mode true always returns 1", () => {
    assert.equal(scaleFactor([0.1, 0.2], { mode: "true" }), 1);
    assert.equal(scaleFactor([0.8], { mode: "true", loudest: 0.8 }), 1);
  });

  test("mode normalised calculates 1 / peak", () => {
    // Peak is 0.5 -> factor 2
    assert.equal(scaleFactor([0.5], { mode: "normalised" }), 2);
    // Peak is 0.25 -> factor 4
    assert.equal(scaleFactor([0.25], { mode: "normalised" }), 4);
  });

  test("mode loudest calculates 1 / loudest", () => {
    // Track peak 0.2, loudest is 0.5 -> factor 2
    assert.equal(scaleFactor([0.2], { mode: "loudest", loudest: 0.5 }), 2);
  });

  test("silent track below floor gets factor 1", () => {
    assert.equal(scaleFactor([0.0005], { mode: "normalised", floor: 0.001 }), 1);
    assert.equal(scaleFactor([], { mode: "normalised" }), 1);
    assert.equal(scaleFactor([0], { mode: "normalised" }), 1);
    // In loudest mode, if the track itself is silent, it gets 1
    assert.equal(scaleFactor([0.0005], { mode: "loudest", loudest: 0.8, floor: 0.001 }), 1);
  });

  test("loudest below floor gets factor 1 in loudest mode", () => {
    assert.equal(scaleFactor([0.5], { mode: "loudest", loudest: 0.0005, floor: 0.001 }), 1);
  });

  test("maxGain cap limits factor", () => {
    // 1 / 0.01 = 100, capped at maxGain 40
    assert.equal(scaleFactor([0.01], { mode: "normalised", maxGain: 40 }), 40);
    // custom maxGain
    assert.equal(scaleFactor([0.01], { mode: "normalised", maxGain: 10 }), 10);
  });
});

describe("labelFor", () => {
  test("factor within 1 % of 1 returns null", () => {
    assert.equal(labelFor(1.0), null);
    assert.equal(labelFor(1.005), null);
    assert.equal(labelFor(0.995), null);
    assert.equal(labelFor(1.01), null);
    assert.equal(labelFor(0.99), null);
  });

  test("factor outside 1 % returns x plus factor with one decimal", () => {
    assert.equal(labelFor(2.4), "x2.4");
    assert.equal(labelFor(4.0), "x4.0");
    assert.equal(labelFor(1.05), "x1.1");
    assert.equal(labelFor(0.5), "x0.5");
  });
});

describe("dbText", () => {
  test("formats 20 * log10(factor) with one decimal and sign always shown", () => {
    assert.equal(dbText(2.4), "+7.6 dB");
    assert.equal(dbText(1.0), "+0.0 dB");
    assert.equal(dbText(2.0), "+6.0 dB");
    assert.equal(dbText(0.5), "-6.0 dB");
  });
});
