import assert from "node:assert/strict";
import test from "node:test";
import { charsThatFit, fitLabel } from "../clip-label.js";

test("fitLabel: text fits unchanged, non-string or empty text, maxChars < 1, maxChars === 1", () => {
  // Fits unchanged
  assert.equal(fitLabel("hello", 10), "hello");
  assert.equal(fitLabel("hello", 5), "hello");

  // Non-string or empty text
  assert.equal(fitLabel("", 10), "");
  assert.equal(fitLabel(null, 10), "");
  assert.equal(fitLabel(undefined, 10), "");
  assert.equal(fitLabel(123, 10), "");

  // maxChars < 1
  assert.equal(fitLabel("hello", 0), "");
  assert.equal(fitLabel("hello", -5), "");

  // maxChars === 1
  assert.equal(fitLabel("hello", 1), "…");
});

test("fitLabel: keeps start and end, middle ellipsis, exact length, odd remainder extra to start", () => {
  // Text: "abcdefghij" (length 10)
  // maxChars: 7
  // avail = 6 -> startLen = 3, endLen = 3
  // "abc" + "…" + "hij" = "abc…hij" (length 7)
  const res7 = fitLabel("abcdefghij", 7);
  assert.equal(res7, "abc…hij");
  assert.equal(res7.length, 7);

  // maxChars: 6 (odd avail = 5)
  // startLen = ceil(5/2) = 3, endLen = floor(5/2) = 2
  // "abc" + "…" + "ij" = "abc…ij" (length 6)
  const res6 = fitLabel("abcdefghij", 6);
  assert.equal(res6, "abc…ij");
  assert.equal(res6.length, 6);

  // maxChars: 5 (even avail = 4)
  // startLen = 2, endLen = 2
  // "ab" + "…" + "ij" = "ab…ij" (length 5)
  const res5 = fitLabel("abcdefghij", 5);
  assert.equal(res5, "ab…ij");
  assert.equal(res5.length, 5);

  // maxChars: 4 (odd avail = 3)
  // startLen = 2, endLen = 1
  // "ab" + "…" + "j" = "ab…j" (length 4)
  const res4 = fitLabel("abcdefghij", 4);
  assert.equal(res4, "ab…j");
  assert.equal(res4.length, 4);

  // maxChars: 3 (even avail = 2)
  // startLen = 1, endLen = 1
  // "a" + "…" + "j" = "a…j" (length 3)
  const res3 = fitLabel("abcdefghij", 3);
  assert.equal(res3, "a…j");
  assert.equal(res3.length, 3);

  // maxChars: 2 (odd avail = 1)
  // startLen = 1, endLen = 0
  // "a" + "…" = "a…" (length 2)
  const res2 = fitLabel("abcdefghij", 2);
  assert.equal(res2, "a…");
  assert.equal(res2.length, 2);
});

test("charsThatFit: normal division, flooring, non-positive and non-finite", () => {
  // Normal cases
  assert.equal(charsThatFit(100, 10), 10);
  assert.equal(charsThatFit(95, 10), 9);
  assert.equal(charsThatFit(10, 15), 0);

  // Zero and negative width or charPx
  assert.equal(charsThatFit(0, 10), 0);
  assert.equal(charsThatFit(-50, 10), 0);
  assert.equal(charsThatFit(100, 0), 0);
  assert.equal(charsThatFit(100, -5), 0);

  // Non-finite or non-number
  assert.equal(charsThatFit(Number.POSITIVE_INFINITY, 10), 0);
  assert.equal(charsThatFit(100, Number.POSITIVE_INFINITY), 0);
  assert.equal(charsThatFit(Number.NaN, 10), 0);
  assert.equal(charsThatFit(100, Number.NaN), 0);
  assert.equal(charsThatFit("100", 10), 0);
  assert.equal(charsThatFit(null, 10), 0);
});
