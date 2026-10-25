import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  DEFAULT_PLAY_BEFORE_S,
  MAX_PLAY_BEFORE_S,
  MIN_PLAY_BEFORE_S,
  normalisePlayBefore,
  PLAY_BEFORE_KEY,
  PLAY_BEFORE_STEP_S,
} from "../play-before.js";

describe("play-before preference (how much P jumps back)", () => {
  test("defaults to 3 seconds when missing, blank or non-finite", () => {
    assert.equal(normalisePlayBefore(null), DEFAULT_PLAY_BEFORE_S);
    assert.equal(normalisePlayBefore(undefined), DEFAULT_PLAY_BEFORE_S);
    assert.equal(normalisePlayBefore(""), DEFAULT_PLAY_BEFORE_S);
    assert.equal(normalisePlayBefore("nonsense"), DEFAULT_PLAY_BEFORE_S);
    assert.equal(normalisePlayBefore(Number.NaN), DEFAULT_PLAY_BEFORE_S);
  });

  test("clamps between min and max bounds", () => {
    assert.equal(normalisePlayBefore(0.1), MIN_PLAY_BEFORE_S);
    assert.equal(normalisePlayBefore(-5), MIN_PLAY_BEFORE_S);
    assert.equal(normalisePlayBefore(20), MAX_PLAY_BEFORE_S);
  });

  test("rounds to the nearest step", () => {
    assert.equal(normalisePlayBefore(2.4), 2.5);
    assert.equal(normalisePlayBefore(2.7), 2.5);
    assert.equal(normalisePlayBefore(2.8), 3.0);
    assert.equal(normalisePlayBefore(5.0), 5.0);
  });

  test("key and step constants", () => {
    assert.equal(PLAY_BEFORE_KEY, "playBeforeS");
    assert.equal(DEFAULT_PLAY_BEFORE_S, 3);
    assert.equal(MIN_PLAY_BEFORE_S, 0.5);
    assert.equal(MAX_PLAY_BEFORE_S, 10);
    assert.equal(PLAY_BEFORE_STEP_S, 0.5);
  });
});
