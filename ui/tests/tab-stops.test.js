import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  cycleScope,
  defaultScope,
  headerFocusPatch,
  mergeStops,
  nextStop,
  prevStop,
  SCOPE_MODE,
  scopeChoice,
  scopeIndicatorKey,
  stopsForScope,
  TAB_SCOPES,
  wordStops,
  wordsAreCurrent,
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

describe("the scope", () => {
  test("cycles word, edge, sound, word", () => {
    assert.deepEqual(TAB_SCOPES, ["word", "edge", "sound"]);
    assert.equal(cycleScope("word"), "edge");
    assert.equal(cycleScope("edge"), "sound");
    assert.equal(cycleScope("sound"), "word");
    assert.equal(cycleScope("junk"), "word");
  });
  test("maps to the server's edit_points modes", () => {
    assert.deepEqual(SCOPE_MODE, { edge: "edges", sound: "transients" });
  });
  test("default is word with a transcript, else edge", () => {
    assert.equal(defaultScope(true), "edge"); // the owner: Tab jumps to the next seam by default
    assert.equal(defaultScope(false), "edge");
  });
  test("a stored choice is used when valid, else the default", () => {
    assert.equal(scopeChoice("sound", true), "sound");
    assert.equal(scopeChoice("nope", false), "edge");
    assert.equal(scopeChoice(null, true), "edge");
  });
  test("old remembered values migrate: transient -> sound, both -> word", () => {
    assert.equal(scopeChoice("transient", true), "sound");
    assert.equal(scopeChoice("transient", false), "sound");
    assert.equal(scopeChoice("both", false), "word");
  });
  test("the indicator has a catalog key per scope", () => {
    assert.equal(scopeIndicatorKey("edge"), "ui.tab_scope.indicator.edge");
  });
});

describe("fresh words", () => {
  test("current only when they were fetched for the head now", () => {
    assert.equal(wordsAreCurrent({ head: "h2", wordsHead: "h2", words: [] }), true);
    assert.equal(wordsAreCurrent({ head: "h2", wordsHead: "h1", words: [] }), false);
    assert.equal(wordsAreCurrent({ head: "h2", wordsHead: null, words: [] }), false);
    assert.equal(wordsAreCurrent({ head: null, wordsHead: null, words: [] }), false);
    assert.equal(wordsAreCurrent(null), false);
  });
});

describe("stops of a scope", () => {
  const words = [
    { s: 100, track: "a" },
    { s: 200, track: "b" },
  ];
  test("word: the focused track's words, all words when that track has none", () => {
    assert.deepEqual(stopsForScope("word", { words, track: "a" }), [100]);
    assert.deepEqual(stopsForScope("word", { words, track: "music" }), [100, 200]);
    assert.deepEqual(stopsForScope("word", { words }), [100, 200]);
  });
  test("edge and sound: the server's stops, sorted and without duplicates", () => {
    assert.deepEqual(stopsForScope("edge", { words, server: [30, 10, 10] }), [10, 30]);
    assert.deepEqual(stopsForScope("sound", { server: [5] }), [5]);
    assert.deepEqual(stopsForScope("sound"), []);
  });
});

describe("header focus", () => {
  test("a header means the timeline context, once", () => {
    assert.deepEqual(headerFocusPatch({ panel: "transcript" }), { panel: "timeline" });
    assert.deepEqual(headerFocusPatch({ panel: "inspector" }), { panel: "timeline" });
    assert.equal(headerFocusPatch({ panel: "timeline" }), null);
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
