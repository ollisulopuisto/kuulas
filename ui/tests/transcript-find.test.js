import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  currentPosition,
  findMatches,
  firstFrom,
  matchedWords,
  nextMatch,
  normalise,
  prevMatch,
} from "../transcript-find.js";

const CASES = JSON.parse(
  readFileSync(fileURLToPath(new URL("./fixtures/find-cases.json", import.meta.url)), "utf8"),
).cases;

describe("findMatches agrees with the Python transcript_find on the shared cases", () => {
  for (const c of CASES) {
    test(c.name, () => {
      assert.deepEqual(
        findMatches(c.words, c.query).map((m) => [...m]),
        c.matches,
      );
    });
  }
});

describe("normalise", () => {
  test("lowercases, drops accents and punctuation, keeps digits and spaces", () => {
    assert.equal(normalise("Äiti, Öljy 2!"), "aiti oljy 2");
  });
});

const matches = [[2], [5, 6], [9]];

describe("stepping", () => {
  test("next is the first match starting after the position, wrapping", () => {
    assert.deepEqual(nextMatch(matches, 2), [5, 6]);
    assert.deepEqual(nextMatch(matches, 9), [2]);
    assert.deepEqual(nextMatch(matches, -1), [2]);
    assert.equal(nextMatch([], 0), null);
  });

  test("previous is the last match starting before the position, wrapping", () => {
    assert.deepEqual(prevMatch(matches, 9), [5, 6]);
    assert.deepEqual(prevMatch(matches, 2), [9]);
    assert.equal(prevMatch([], 0), null);
  });

  test("a search starts at the first match at or after the cursor word, else wraps", () => {
    assert.deepEqual(firstFrom(matches, 5), [5, 6]);
    assert.deepEqual(firstFrom(matches, 3), [5, 6]);
    assert.deepEqual(firstFrom(matches, 10), [2]);
    assert.equal(firstFrom([], 0), null);
  });
});

describe("the readout and the highlights", () => {
  test("n of m is the 1-based place of the current match", () => {
    assert.deepEqual(currentPosition(matches, [5, 6]), { n: 2, m: 3 });
    assert.deepEqual(currentPosition(matches, null), { n: 0, m: 3 });
    assert.deepEqual(currentPosition([], null), { n: 0, m: 0 });
  });

  test("every word of every match is highlighted", () => {
    assert.deepEqual(
      [...matchedWords(matches)].sort((a, b) => a - b),
      [2, 5, 6, 9],
    );
  });
});
