import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { markDrawing, placeMark } from "../marks.js";

describe("placing a mark with the ghost of the last cut (T69)", () => {
  const none = {
    inPoint: null,
    outPoint: null,
    ghost: null,
    guessedMarks: { in: null, out: null },
  };
  const guessedIn = {
    inPoint: 100,
    outPoint: 500,
    ghost: { frame: 100 },
    guessedMarks: { in: 100, out: null },
  };
  test("without a ghost it is the plain rule and nothing is guessed", () => {
    assert.deepEqual(placeMark(none, "out", 500), {
      inPoint: null,
      outPoint: 500,
      guessedMarks: { in: null, out: null },
    });
  });
  test("only OUT, with the ghost earlier: IN goes to the ghost and is guessed", () => {
    assert.deepEqual(placeMark({ ...none, ghost: { frame: 100 } }, "out", 500), {
      inPoint: 100,
      outPoint: 500,
      guessedMarks: { in: 100, out: null },
    });
  });
  test("only IN, with the ghost later: OUT goes to the ghost and is guessed", () => {
    assert.deepEqual(placeMark({ ...none, ghost: { frame: 900 } }, "in", 500), {
      inPoint: 500,
      outPoint: 900,
      guessedMarks: { in: null, out: 900 },
    });
  });
  test("an explicit partner wins over the ghost", () => {
    assert.deepEqual(placeMark({ ...none, inPoint: 300, ghost: { frame: 100 } }, "out", 500), {
      inPoint: 300,
      outPoint: 500,
      guessedMarks: { in: null, out: null },
    });
  });
  test("a ghost on the wrong side guesses nothing", () => {
    assert.equal(placeMark({ ...none, ghost: { frame: 900 } }, "out", 500).inPoint, null);
    assert.equal(placeMark({ ...none, ghost: { frame: 100 } }, "in", 500).outPoint, null);
  });
  test("setting the guessed mark by hand makes it explicit", () => {
    assert.deepEqual(placeMark(guessedIn, "in", 100).guessedMarks, { in: null, out: null });
  });
  test("a guess stays a guess when the other mark is set again", () => {
    const next = placeMark(guessedIn, "out", 700);
    assert.equal(next.inPoint, 100);
    assert.deepEqual(next.guessedMarks, { in: 100, out: null });
  });
  test("an in mark that drops the old out mark can guess a new one", () => {
    assert.deepEqual(placeMark({ ...none, outPoint: 300, ghost: { frame: 900 } }, "in", 500), {
      inPoint: 500,
      outPoint: 900,
      guessedMarks: { in: null, out: 900 },
    });
  });
});

describe("drawing guessed marks", () => {
  test("a mark equal to its guessed frame is drawn as a guess", () => {
    const d = markDrawing({ inPoint: 100, outPoint: 500, guessedMarks: { in: 100, out: null } });
    assert.deepEqual(d.guessed, { in: true, out: false });
    assert.deepEqual(d.range, { start: 100, end: 500 });
  });
  test("a mark moved by hand since is not a guess; no record means none guessed", () => {
    assert.deepEqual(
      markDrawing({ inPoint: 120, outPoint: 500, guessedMarks: { in: 100, out: null } }).guessed,
      { in: false, out: false },
    );
    assert.deepEqual(markDrawing({ inPoint: 1, outPoint: 2 }).guessed, { in: false, out: false });
  });
});
