import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  cycleTarget,
  defaultTarget,
  mergeStops,
  nextStop,
  prevStop,
  TAB_TARGETS,
  targetChoice,
  wordStops,
} from "../tab-stops.js";

describe("next and previous stop", () => {
  const stops = [10, 20, 30];
  test("strictly after the frame, null at the end", () => {
    assert.equal(nextStop(stops, 0), 10);
    assert.equal(nextStop(stops, 10), 20);
    assert.equal(nextStop(stops, 15), 20);
    assert.equal(nextStop(stops, 30), null);
    assert.equal(nextStop([], 0), null);
  });
  test("strictly before the frame, null at the start", () => {
    assert.equal(prevStop(stops, 40), 30);
    assert.equal(prevStop(stops, 30), 20);
    assert.equal(prevStop(stops, 15), 10);
    assert.equal(prevStop(stops, 10), null);
    assert.equal(prevStop([], 5), null);
  });
  test("missing lists are empty", () => {
    assert.equal(nextStop(null, 0), null);
    assert.equal(prevStop(undefined, 0), null);
  });
});

describe("merging stops", () => {
  test("sorted, without duplicates, whatever the order of the lists", () => {
    assert.deepEqual(mergeStops([30, 10], [20, 10], null, []), [10, 20, 30]);
    assert.deepEqual(mergeStops(), []);
  });
});

describe("the target mode", () => {
  test("cycles word, transient, both, word", () => {
    assert.deepEqual(TAB_TARGETS, ["word", "transient", "both"]);
    assert.equal(cycleTarget("word"), "transient");
    assert.equal(cycleTarget("transient"), "both");
    assert.equal(cycleTarget("both"), "word");
    assert.equal(cycleTarget("junk"), "word");
  });
  test("default is word with a transcript, else transient", () => {
    assert.equal(defaultTarget(true), "word");
    assert.equal(defaultTarget(false), "transient");
  });
  test("a stored choice is used when valid, else the default", () => {
    assert.equal(targetChoice("both", true), "both");
    assert.equal(targetChoice("nope", false), "transient");
    assert.equal(targetChoice(null, true), "word");
  });
});

describe("word stops", () => {
  const words = [
    { s: 300, track: "a" },
    { s: 100, track: "a" },
    { s: 100, track: "b" },
    { s: 200, track: "b", muted: true },
  ];
  test("start frames of the words, sorted, muted ones left out", () => {
    assert.deepEqual(wordStops(words), [100, 300]);
  });
  test("of one track when asked", () => {
    assert.deepEqual(wordStops(words, "b"), [100]);
    assert.deepEqual(wordStops(null), []);
  });
});
