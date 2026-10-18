import assert from "node:assert/strict";
import test from "node:test";
import { stateRuns, visibleCount, wordState } from "../focus-words.js";

test("wordState: no focus, one focus id, several, hide on and off", () => {
  const word1 = { track: "t1", w: "hello", s: 0, e: 100 };
  const word2 = { track: "t2", w: "world", s: 100, e: 200 };

  // No focus: null, undefined, empty array -> always "normal"
  assert.equal(wordState(word1, null), "normal");
  assert.equal(wordState(word1, undefined), "normal");
  assert.equal(wordState(word1, []), "normal");
  assert.equal(wordState(word2, [], true), "normal");

  // One focus id
  assert.equal(wordState(word1, ["t1"]), "normal");
  assert.equal(wordState(word2, ["t1"]), "dim");
  assert.equal(wordState(word2, ["t1"], false), "dim");
  assert.equal(wordState(word2, ["t1"], true), "hidden");

  // Several focus ids
  assert.equal(wordState(word1, ["t1", "t3"]), "normal");
  assert.equal(wordState(word2, ["t1", "t3"]), "dim");
  assert.equal(wordState(word2, ["t1", "t3"], true), "hidden");
});

test("stateRuns: alternating sequence, runs at start and end, empty input", () => {
  // Empty input
  assert.deepEqual(stateRuns([], ["t1"]), []);
  assert.deepEqual(stateRuns(null, ["t1"]), []);

  const words = [
    { track: "t1", w: "a" },
    { track: "t1", w: "b" },
    { track: "t2", w: "c" },
    { track: "t1", w: "d" },
    { track: "t2", w: "e" },
    { track: "t2", w: "f" },
  ];

  // focus ["t1"], hide = false
  // 0: t1 (normal), 1: t1 (normal) -> run { state: "normal", first: 0, last: 1 }
  // 2: t2 (dim)                    -> run { state: "dim", first: 2, last: 2 }
  // 3: t1 (normal)                 -> run { state: "normal", first: 3, last: 3 }
  // 4: t2 (dim), 5: t2 (dim)       -> run { state: "dim", first: 4, last: 5 }
  const runsDim = stateRuns(words, ["t1"], false);
  assert.deepEqual(runsDim, [
    { state: "normal", first: 0, last: 1 },
    { state: "dim", first: 2, last: 2 },
    { state: "normal", first: 3, last: 3 },
    { state: "dim", first: 4, last: 5 },
  ]);

  // focus ["t1"], hide = true
  const runsHidden = stateRuns(words, ["t1"], true);
  assert.deepEqual(runsHidden, [
    { state: "normal", first: 0, last: 1 },
    { state: "hidden", first: 2, last: 2 },
    { state: "normal", first: 3, last: 3 },
    { state: "hidden", first: 4, last: 5 },
  ]);

  // Single run (all same state)
  const allNormal = [
    { track: "t1", w: "a" },
    { track: "t1", w: "b" },
  ];
  assert.deepEqual(stateRuns(allNormal, ["t1"]), [{ state: "normal", first: 0, last: 1 }]);
});

test("visibleCount: empty input, hide on and off", () => {
  const words = [
    { track: "t1", w: "a" },
    { track: "t2", w: "b" },
    { track: "t1", w: "c" },
  ];

  assert.equal(visibleCount([], ["t1"]), 0);
  assert.equal(visibleCount(null, ["t1"]), 0);

  // Without hide: all words are visible (dim words are still visible)
  assert.equal(visibleCount(words, ["t1"], false), 3);
  assert.equal(visibleCount(words, null, false), 3);

  // With hide: only focused track words are visible
  assert.equal(visibleCount(words, ["t1"], true), 2);
  assert.equal(visibleCount(words, ["t2"], true), 1);
  assert.equal(visibleCount(words, ["t3"], true), 0);
  assert.equal(visibleCount(words, [], true), 3);
});

test("immutability of inputs", () => {
  const words = Object.freeze([
    Object.freeze({ track: "t1", w: "a" }),
    Object.freeze({ track: "t2", w: "b" }),
  ]);
  const focus = Object.freeze(["t1"]);

  wordState(words[0], focus);
  stateRuns(words, focus, false);
  visibleCount(words, focus, true);
  assert.equal(words.length, 2);
});
