import assert from "node:assert/strict";
import test from "node:test";
import { highlightSegments } from "../highlight-segments.js";

test("highlightSegments: example from spec - 'Export mix (options)…' with 'mix opt'", () => {
  const text = "Export mix (options)…";
  const segments = highlightSegments(text, "mix opt");
  assert.equal(segments.map((s) => s.text).join(""), text);
  assert.deepEqual(segments, [
    { text: "Export ", match: false },
    { text: "mix", match: true },
    { text: " (", match: false },
    { text: "opt", match: true },
    { text: "ions)…", match: false },
  ]);
});

test("highlightSegments: example from spec - 'Jump back and play' with 'jump play'", () => {
  const text = "Jump back and play";
  const segments = highlightSegments(text, "jump play");
  assert.equal(segments.map((s) => s.text).join(""), text);
  assert.deepEqual(segments, [
    { text: "Jump", match: true },
    { text: " back and ", match: false },
    { text: "play", match: true },
  ]);
});

test("highlightSegments: example from spec - 'Näytä' with 'nayta' matches the whole word", () => {
  const text = "Näytä";
  const segments = highlightSegments(text, "nayta");
  assert.equal(segments.map((s) => s.text).join(""), text);
  assert.deepEqual(segments, [{ text: "Näytä", match: true }]);
});

test("highlightSegments: overlapping matches are merged into one segment", () => {
  const text = "understand";
  // "under" (0..5) and "stand" (5..10) touch, "der" (2..5) overlaps
  const segments = highlightSegments(text, "under der");
  assert.equal(segments.map((s) => s.text).join(""), text);
  assert.deepEqual(segments, [
    { text: "under", match: true },
    { text: "stand", match: false },
  ]);
});

test("highlightSegments: touching matches are merged into one segment", () => {
  const text = "playhead";
  // "play" (0..4) and "head" (4..8) touch -> merged into 0..8
  const segments = highlightSegments(text, "play head");
  assert.equal(segments.map((s) => s.text).join(""), text);
  assert.deepEqual(segments, [{ text: "playhead", match: true }]);
});

test("highlightSegments: multiple occurrences of the same word", () => {
  const text = "la la la";
  const segments = highlightSegments(text, "la");
  assert.equal(segments.map((s) => s.text).join(""), text);
  assert.deepEqual(segments, [
    { text: "la", match: true },
    { text: " ", match: false },
    { text: "la", match: true },
    { text: " ", match: false },
    { text: "la", match: true },
  ]);
});

test("highlightSegments: special unicode characters (İ and ß, Finnish ä ö å)", () => {
  // Turkish dotted capital I
  const text1 = "İpek yolları";
  const segments1 = highlightSegments(text1, "ipek");
  assert.equal(segments1.map((s) => s.text).join(""), text1);
  assert.deepEqual(segments1, [
    { text: "İpek", match: true },
    { text: " yolları", match: false },
  ]);

  // Turkish dotless small i (ı)
  const text2 = "ılık su";
  const segments2 = highlightSegments(text2, "ılık");
  assert.equal(segments2.map((s) => s.text).join(""), text2);
  assert.deepEqual(segments2, [
    { text: "ılık", match: true },
    { text: " su", match: false },
  ]);

  // German ß
  const text3 = "Große Straße";
  const segments3 = highlightSegments(text3, "große straße");
  assert.equal(segments3.map((s) => s.text).join(""), text3);
  assert.deepEqual(segments3, [
    { text: "Große", match: true },
    { text: " ", match: false },
    { text: "Straße", match: true },
  ]);

  // Accents in French/Spanish
  const text4 = "Crème brûlée";
  const segments4 = highlightSegments(text4, "creme brulee");
  assert.equal(segments4.map((s) => s.text).join(""), text4);
  assert.deepEqual(segments4, [
    { text: "Crème", match: true },
    { text: " ", match: false },
    { text: "brûlée", match: true },
  ]);
});

test("highlightSegments: empty or whitespace query gives one segment with match: false", () => {
  const text = "Sample text";
  assert.deepEqual(highlightSegments(text, ""), [{ text: "Sample text", match: false }]);
  assert.deepEqual(highlightSegments(text, "   "), [{ text: "Sample text", match: false }]);
  assert.deepEqual(highlightSegments(text, "\t\n"), [{ text: "Sample text", match: false }]);
});

test("highlightSegments: no match gives one segment with match: false", () => {
  const text = "Hello world";
  assert.deepEqual(highlightSegments(text, "xyz foo"), [{ text: "Hello world", match: false }]);
});

test("highlightSegments: empty text gives []", () => {
  assert.deepEqual(highlightSegments("", "foo"), []);
  assert.deepEqual(highlightSegments(null, "foo"), []);
  assert.deepEqual(highlightSegments(undefined, "foo"), []);
});

test("highlightSegments: inputs are never mutated", () => {
  const text = "Hello World";
  const query = "world";
  const segments = highlightSegments(text, query);
  assert.equal(segments.length, 2);
});
