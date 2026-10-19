import assert from "node:assert/strict";
import { test } from "node:test";
import {
  averageWordFrames,
  clipWordIndices,
  ELLIPSIS,
  fitWord,
  layoutClipWords,
  WORD_MIN_AVG_PX,
  wordsWideEnough,
} from "../clip-words.js";

// A fake text measure: 6 px per character.
const measure = (text) => text.length * 6;
const word = (w, s, e, track = "a", clip = "c1") => ({ w, s, e, track, clip });

test("the threshold is about 28 px of average word width", () => {
  assert.equal(WORD_MIN_AVG_PX, 28);
});

test("averageWordFrames is the mean word length; 0 for no words", () => {
  assert.equal(averageWordFrames([]), 0);
  assert.equal(averageWordFrames(undefined), 0);
  assert.equal(averageWordFrames([word("a", 0, 100), word("b", 200, 500)]), 200);
});

test("words are drawn only when the average word is wide enough", () => {
  // Zoom is frames per px: 10000 frames per word at 100 frames/px = 100 px.
  assert.equal(wordsWideEnough(10000, 100), true);
  assert.equal(wordsWideEnough(2800, 100), true);
  assert.equal(wordsWideEnough(2799, 100), false);
  assert.equal(wordsWideEnough(0, 100), false);
  assert.equal(wordsWideEnough(10000, 0), false);
});

test("fitWord: whole word, then an ellipsis, then nothing", () => {
  assert.equal(fitWord("hello", 30, measure), "hello");
  assert.equal(fitWord("hello", 24, measure), `hel${ELLIPSIS}`);
  assert.equal(fitWord("hello", 12, measure), `h${ELLIPSIS}`);
  assert.equal(fitWord("hello", 6, measure), ELLIPSIS);
  assert.equal(fitWord("hello", 5, measure), "");
  assert.equal(fitWord("", 100, measure), "");
  assert.equal(fitWord("hello", 0, measure), "");
});

test("fitWord never returns text wider than the room", () => {
  for (let room = 0; room < 40; room++) {
    const out = fitWord("kirjoittaminen", room, measure);
    assert.ok(measure(out) <= room, `${room}: ${out}`);
  }
});

const words = [
  word("one", 0, 100),
  word("two", 100, 200),
  word("three", 200, 300),
  word("four", 300, 400),
  word("other", 150, 250, "b", "c2"),
  word("five", 400, 500),
];
const sorted = [...words].sort((x, y) => x.s - y.s);
const names = (indices) => indices.map((i) => sorted[i].w);

test("clipWordIndices: only this track and clip, only the visible stretch", () => {
  const got = clipWordIndices(sorted, {
    trackId: "a",
    clip: { id: "c1", start: 0, length: 500 },
    from: 100,
    to: 300,
    lookback: 0,
  });
  assert.deepEqual(names(got), ["two", "three"]);
});

test("clipWordIndices: a word that starts before the view but ends inside it is kept", () => {
  const got = clipWordIndices(sorted, {
    trackId: "a",
    clip: { id: "c1", start: 0, length: 500 },
    from: 250,
    to: 350,
    lookback: 100,
  });
  assert.deepEqual(names(got), ["three", "four"]);
});

test("clipWordIndices honours trims and moves: words outside the clip's span are dropped", () => {
  // The clip was trimmed to 100..300 (and the words list is one edit behind).
  const got = clipWordIndices(sorted, {
    trackId: "a",
    clip: { id: "c1", start: 100, length: 200 },
    from: 0,
    to: 1000,
    lookback: 1000,
  });
  assert.deepEqual(names(got), ["two", "three"]);
});

test("clipWordIndices: no words for the clip, or no words list, gives nothing", () => {
  const clip = { id: "c9", start: 0, length: 500 };
  assert.deepEqual(
    clipWordIndices(sorted, { trackId: "zzz", clip, from: 0, to: 500, lookback: 0 }),
    [],
  );
  assert.deepEqual(clipWordIndices([], { trackId: "a", clip, from: 0, to: 5 }), []);
  assert.deepEqual(clipWordIndices(undefined, { trackId: "a", clip, from: 0, to: 5 }), []);
});

test("clipWordIndices uses a binary search: a long list costs few looks", () => {
  let reads = 0;
  const many = Array.from({ length: 100000 }, (_, i) => ({
    get s() {
      reads++;
      return i * 10;
    },
    e: i * 10 + 10,
    w: "x",
    track: "a",
    clip: "c1",
  }));
  const got = clipWordIndices(many, {
    trackId: "a",
    clip: { id: "c1", start: 0, length: 1_000_000 },
    from: 500_000,
    to: 500_100,
    lookback: 0,
  });
  assert.equal(got.length, 10);
  assert.ok(reads < 200, `read ${reads} starts`);
});

const base = {
  words: sorted,
  trackId: "a",
  clip: { id: "c1", start: 0, length: 500 },
  scroll: 0,
  zoom: 1,
  viewWidth: 1000,
  lookback: 1000,
  measure,
  current: -1,
  selected: null,
};

test("layoutClipWords: each word at its own start, cut at its own end", () => {
  // 100 frames at 5 frames/px = 20 px, less a 2 px gap = 18 px = three characters.
  const items = layoutClipWords({ ...base, zoom: 5 });
  assert.deepEqual(
    items.map((i) => i.text),
    ["one", "two", `th${ELLIPSIS}`, `fo${ELLIPSIS}`, `fi${ELLIPSIS}`],
  );
  assert.equal(items[0].x, 0);
  assert.equal(items[1].x, 20);
  for (let i = 1; i < items.length; i++) {
    assert.ok(items[i].x >= items[i - 1].x + items[i - 1].w, "words overlap");
  }
});

test("layoutClipWords skips words that cannot fit even an ellipsis", () => {
  assert.deepEqual(layoutClipWords({ ...base, zoom: 25 }), []); // 4 px per word
});

test("layoutClipWords marks the current word and the selected words", () => {
  const at = (text) => sorted.findIndex((w) => w.w === text);
  const items = layoutClipWords({
    ...base,
    zoom: 5,
    current: at("two"),
    selected: [at("three"), at("four")],
  });
  const marks = Object.fromEntries(items.map((i) => [sorted[i.index].w, i.mark]));
  assert.equal(marks.one, "plain");
  assert.equal(marks.two, "current");
  assert.equal(marks.three, "selected");
  assert.equal(marks.four, "selected");
});

test("layoutClipWords only lays out what is on screen", () => {
  const items = layoutClipWords({ ...base, zoom: 5, scroll: 200, viewWidth: 40 });
  assert.deepEqual(names(items.map((i) => i.index)), ["three", "four"]);
});
