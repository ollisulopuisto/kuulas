import assert from "node:assert/strict";
import test from "node:test";
import { clearGhost, rememberCut, resolveMark } from "../ghost-marker.js";

test("rememberCut returns { frame } and clearGhost returns null", () => {
  assert.deepEqual(rememberCut(100), { frame: 100 });
  assert.equal(clearGhost(), null);
});

test("extend cut forward: setting out while in is null and ghost < out sets in and guessed.in", () => {
  const ghost = rememberCut(100);
  const marks = { in: null, out: null };
  const res = resolveMark(ghost, marks, "out", 250);

  assert.deepEqual(res, {
    in: 100,
    out: 250,
    guessed: { in: true, out: false },
  });
});

test("extend cut backwards: setting in while out is null and ghost > in sets out and guessed.out", () => {
  const ghost = rememberCut(500);
  const marks = { in: null, out: null };
  const res = resolveMark(ghost, marks, "in", 300);

  assert.deepEqual(res, {
    in: 300,
    out: 500,
    guessed: { in: false, out: true },
  });
});

test("wrong side: ghost >= out when setting out guesses nothing", () => {
  const ghost = rememberCut(300);
  const marks = { in: null, out: null };
  const res = resolveMark(ghost, marks, "out", 200);

  assert.deepEqual(res, {
    in: null,
    out: 200,
    guessed: { in: false, out: false },
  });

  const resEqual = resolveMark(rememberCut(200), marks, "out", 200);
  assert.deepEqual(resEqual, {
    in: null,
    out: 200,
    guessed: { in: false, out: false },
  });
});

test("wrong side: ghost <= in when setting in guesses nothing", () => {
  const ghost = rememberCut(100);
  const marks = { in: null, out: null };
  const res = resolveMark(ghost, marks, "in", 200);

  assert.deepEqual(res, {
    in: 200,
    out: null,
    guessed: { in: false, out: false },
  });

  const resEqual = resolveMark(rememberCut(200), marks, "in", 200);
  assert.deepEqual(resEqual, {
    in: 200,
    out: null,
    guessed: { in: false, out: false },
  });
});

test("both marks already set: setting mark does not invoke ghost", () => {
  const ghost = rememberCut(100);
  const marks = { in: 50, out: 200, guessed: { in: false, out: false } };

  const resOut = resolveMark(ghost, marks, "out", 250);
  assert.deepEqual(resOut, {
    in: 50,
    out: 250,
    guessed: { in: false, out: false },
  });

  const resIn = resolveMark(rememberCut(500), marks, "in", 80);
  assert.deepEqual(resIn, {
    in: 80,
    out: 200,
    guessed: { in: false, out: false },
  });
});

test("explicit mark overrides a guess", () => {
  const ghost = rememberCut(100);
  const marks = { in: 100, out: 250, guessed: { in: true, out: false } };

  // Explicitly setting "in" clears guessed.in
  const resIn = resolveMark(ghost, marks, "in", 80);
  assert.deepEqual(resIn, {
    in: 80,
    out: 250,
    guessed: { in: false, out: false },
  });

  // Explicitly setting "out" when guessed.out was true clears guessed.out
  const marksGuessedOut = { in: 50, out: 500, guessed: { in: false, out: true } };
  const resOut = resolveMark(ghost, marksGuessedOut, "out", 450);
  assert.deepEqual(resOut, {
    in: 50,
    out: 450,
    guessed: { in: false, out: false },
  });
});

test("no ghost: only asked mark is set", () => {
  const marks = { in: null, out: null };
  const resIn = resolveMark(null, marks, "in", 150);
  assert.deepEqual(resIn, {
    in: 150,
    out: null,
    guessed: { in: false, out: false },
  });

  const resOut = resolveMark(undefined, marks, "out", 350);
  assert.deepEqual(resOut, {
    in: null,
    out: 350,
    guessed: { in: false, out: false },
  });
});

test("not mutating input: frozen input objects", () => {
  const ghost = Object.freeze({ frame: 100 });
  const guessed = Object.freeze({ in: false, out: false });
  const marks = Object.freeze({ in: null, out: null, guessed });

  const res = resolveMark(ghost, marks, "out", 250);
  assert.notEqual(res, marks);
  assert.deepEqual(res, {
    in: 100,
    out: 250,
    guessed: { in: true, out: false },
  });
});
