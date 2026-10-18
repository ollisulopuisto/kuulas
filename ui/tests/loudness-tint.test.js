import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { curveRuns, loudnessState } from "../loudness-tint.js";

describe("loudnessState", () => {
  test("within 2 LUFS of target is ok, boundary inclusive", () => {
    assert.equal(loudnessState(-18, -16), "ok");
    assert.equal(loudnessState(-14, -16), "ok");
    assert.equal(loudnessState(-16, -16), "ok");
  });

  test("between 2 and 5 LUFS away is notice, both bounds inclusive", () => {
    assert.equal(loudnessState(-18.1, -16), "notice");
    assert.equal(loudnessState(-21, -16), "notice");
    assert.equal(loudnessState(-11, -16), "notice");
    assert.equal(loudnessState(-20, -15), "notice");
  });

  test("more than 5 LUFS away is warn", () => {
    assert.equal(loudnessState(-21.1, -16), "warn");
    assert.equal(loudnessState(-26, -16), "warn");
    assert.equal(loudnessState(-5, -16), "warn");
  });

  test("negative distances count the same way", () => {
    assert.equal(loudnessState(-14, -16), "ok");
    assert.equal(loudnessState(-11, -16), "notice");
    assert.equal(loudnessState(-10, -16), "warn");
    assert.equal(loudnessState(-19, -16), "notice");
    assert.equal(loudnessState(-21, -16), "notice");
    assert.equal(loudnessState(-22, -16), "warn");
  });

  test("null, undefined or non-finite values give none", () => {
    assert.equal(loudnessState(null, -16), "none");
    assert.equal(loudnessState(undefined, -16), "none");
    assert.equal(loudnessState(NaN, -16), "none");
    assert.equal(loudnessState(Infinity, -16), "none");
    assert.equal(loudnessState(-16, null), "none");
    assert.equal(loudnessState(-16, undefined), "none");
    assert.equal(loudnessState(-16, NaN), "none");
    assert.equal(loudnessState(-16, Infinity), "none");
  });
});

describe("curveRuns", () => {
  test("empty input gives an empty array", () => {
    assert.deepEqual(curveRuns([], -16), []);
  });

  test("a single point is one run with start === end", () => {
    assert.deepEqual(curveRuns([[42, -18]], -16), [{ start: 42, end: 42, state: "ok" }]);
  });

  test("a curve that goes ok, notice, warn, ok gives four runs", () => {
    assert.deepEqual(
      curveRuns(
        [
          [0, -18],
          [1, -20],
          [2, -22],
          [3, -17],
        ],
        -16,
      ),
      [
        { start: 0, end: 0, state: "ok" },
        { start: 1, end: 1, state: "notice" },
        { start: 2, end: 2, state: "warn" },
        { start: 3, end: 3, state: "ok" },
      ],
    );
  });

  test("consecutive points with the same state merge into one run", () => {
    assert.deepEqual(
      curveRuns(
        [
          [0, -18],
          [1, -17.5],
          [2, -20],
          [3, -19],
        ],
        -16,
      ),
      [
        { start: 0, end: 1, state: "ok" },
        { start: 2, end: 3, state: "notice" },
      ],
    );
  });

  test("none points are kept as runs of state none, consecutive ones merged", () => {
    assert.deepEqual(
      curveRuns(
        [
          [0, -18],
          [1, null],
          [2, undefined],
          [3, -17],
        ],
        -16,
      ),
      [
        { start: 0, end: 0, state: "ok" },
        { start: 1, end: 2, state: "none" },
        { start: 3, end: 3, state: "ok" },
      ],
    );
  });

  test("a null target makes every point none, merged into one run", () => {
    assert.deepEqual(
      curveRuns(
        [
          [0, -18],
          [1, -20],
        ],
        null,
      ),
      [{ start: 0, end: 1, state: "none" }],
    );
  });
});
