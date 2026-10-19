import assert from "node:assert/strict";
import test from "node:test";
import { findFalseStarts } from "../false-starts.js";

function makeWords(texts, { startFrame = 0, wordDuration = 1000, gap = 200 } = {}) {
  let cur = startFrame;
  return texts.map((text) => {
    const s = cur;
    const e = cur + wordDuration;
    cur = e + gap;
    return { text, s, e };
  });
}

test("findFalseStarts: example from spec - 'I think we, I think we should go'", () => {
  const words = makeWords(["I", "think", "we,", "I", "think", "we", "should", "go"]);
  const hits = findFalseStarts(words);
  assert.equal(hits.length, 1);
  assert.deepEqual(hits[0], {
    index: 0,
    count: 3,
    s: words[0].s,
    e: words[2].e,
    repeatIndex: 3,
  });
});

test("findFalseStarts: repeat after 1, 2, or 3 broken attempt filler words", () => {
  // 1 filler word: j = i + n + 1
  const words1 = makeWords(["I", "think", "uh", "I", "think", "now"]);
  const hits1 = findFalseStarts(words1);
  assert.equal(hits1.length, 1);
  assert.deepEqual(hits1[0], {
    index: 0,
    count: 3, // words 0, 1, 2 are in the broken attempt
    s: words1[0].s,
    e: words1[2].e,
    repeatIndex: 3,
  });

  // 2 filler words: j = i + n + 2
  const words2 = makeWords(["we", "must", "uh", "well", "we", "must", "act"]);
  const hits2 = findFalseStarts(words2);
  assert.equal(hits2.length, 1);
  assert.deepEqual(hits2[0], {
    index: 0,
    count: 4, // words 0, 1, 2, 3
    s: words2[0].s,
    e: words2[3].e,
    repeatIndex: 4,
  });

  // 3 filler words: j = i + n + 3
  const words3 = makeWords(["we", "must", "uh", "well", "now", "we", "must", "act"]);
  const hits3 = findFalseStarts(words3);
  assert.equal(hits3.length, 1);
  assert.deepEqual(hits3[0], {
    index: 0,
    count: 5, // words 0, 1, 2, 3, 4
    s: words3[0].s,
    e: words3[4].e,
    repeatIndex: 5,
  });

  // 4 filler words: exceeds 3, not counted as repeat of the false start
  const words4 = makeWords(["we", "must", "one", "two", "three", "four", "we", "must"]);
  const hits4 = findFalseStarts(words4);
  assert.equal(hits4.length, 0);
});

test("findFalseStarts: longest n >= minWords chosen for a given i", () => {
  // At i=0, we have matching 2 words ("we", "can") and matching 3 words ("we", "can", "definitely")
  const words = makeWords(["We", "can", "definitely", "we", "can", "definitely", "do", "it"]);
  const hits = findFalseStarts(words);
  assert.equal(hits.length, 1);
  assert.deepEqual(hits[0], {
    index: 0,
    count: 3,
    s: words[0].s,
    e: words[2].e,
    repeatIndex: 3,
  });
});

test("findFalseStarts: skips i that lies inside a range already reported", () => {
  const words = makeWords([
    "I",
    "believe",
    "that",
    "I",
    "believe",
    "that", // 0..2 false start, 3..5 repeat
    "and",
    "then",
    "we",
    "go",
    "we",
    "go", // 8..9 false start, 10..11 repeat
  ]);
  const hits = findFalseStarts(words);
  assert.equal(hits.length, 2);
  assert.equal(hits[0].index, 0);
  assert.equal(hits[0].count, 3);
  assert.equal(hits[0].repeatIndex, 3);

  assert.equal(hits[1].index, 8);
  assert.equal(hits[1].count, 2);
  assert.equal(hits[1].repeatIndex, 10);
});

test("findFalseStarts: cleaning handles punctuation, case and unicode letters (Finnish)", () => {
  const words = makeWords(["”Tämä", "päivä,", "tämä", "PÄIVÄ!", "on", "hyvä"]);
  const hits = findFalseStarts(words);
  assert.equal(hits.length, 1);
  assert.deepEqual(hits[0], {
    index: 0,
    count: 2,
    s: words[0].s,
    e: words[1].e,
    repeatIndex: 2,
  });
});

test("findFalseStarts: words that clean to '' are skipped but still count as positions", () => {
  const words = [
    { text: "...", s: 0, e: 100 },
    { text: "I", s: 200, e: 300 },
    { text: "know,", s: 400, e: 500 },
    { text: "I", s: 600, e: 700 },
    { text: "know", s: 800, e: 900 },
  ];
  const hits = findFalseStarts(words);
  assert.equal(hits.length, 1);
  assert.deepEqual(hits[0], {
    index: 1, // index 0 was "..." which cleaned to "", so index 1 is starting point
    count: 2, // words 1 and 2
    s: 200,
    e: 500,
    repeatIndex: 3,
  });
});

test("findFalseStarts: maxGap constraint accepts gap <= maxGap and rejects gap > maxGap", () => {
  // Gap between words[j-1].e and words[j].s
  const wordsAccept = [
    { text: "let's", s: 0, e: 1000 },
    { text: "try", s: 1200, e: 2000 },
    { text: "let's", s: 50000, e: 51000 }, // gap = 50000 - 2000 = 48000 (<= maxGap 48000)
    { text: "try", s: 51200, e: 52000 },
  ];
  const hitsAccept = findFalseStarts(wordsAccept);
  assert.equal(hitsAccept.length, 1);

  const wordsReject = [
    { text: "let's", s: 0, e: 1000 },
    { text: "try", s: 1200, e: 2000 },
    { text: "let's", s: 50001, e: 51001 }, // gap = 50001 - 2000 = 48001 (> maxGap 48000)
    { text: "try", s: 51200, e: 52000 },
  ];
  const hitsReject = findFalseStarts(wordsReject);
  assert.equal(hitsReject.length, 0);

  // Custom maxGap option
  const hitsCustom = findFalseStarts(wordsReject, { maxGap: 50000 });
  assert.equal(hitsCustom.length, 1);
});

test("findFalseStarts: minWords option", () => {
  const singleRepeat = makeWords(["hello", "hello", "there"]);
  // default minWords = 2: single repeated word is not a hit
  assert.equal(findFalseStarts(singleRepeat).length, 0);

  // minWords = 1: accepts single word repeat
  const hits1 = findFalseStarts(singleRepeat, { minWords: 1 });
  assert.equal(hits1.length, 1);
  assert.deepEqual(hits1[0], {
    index: 0,
    count: 1,
    s: singleRepeat[0].s,
    e: singleRepeat[0].e,
    repeatIndex: 1,
  });
});

test("findFalseStarts: validation errors", () => {
  assert.throws(() => findFalseStarts([], { minWords: 0 }), /minWords/i);
  assert.throws(() => findFalseStarts([], { minWords: -1 }), /minWords/i);
  assert.throws(() => findFalseStarts([], { maxGap: -1 }), /maxGap/i);

  assert.throws(() => findFalseStarts([{ s: 0, e: 100 }]), /text/i);
  assert.throws(() => findFalseStarts([{ text: "word", e: 100 }]), /s/i);
  assert.throws(() => findFalseStarts([{ text: "word", s: 0 }]), /e/i);
  assert.throws(() => findFalseStarts([{ text: 123, s: 0, e: 100 }]), /text/i);
  assert.throws(() => findFalseStarts([{ text: "word", s: "0", e: 100 }]), /s/i);
  assert.throws(() => findFalseStarts([{ text: "word", s: 0, e: NaN }]), /e/i);
});

test("findFalseStarts: empty or null input returns []", () => {
  assert.deepEqual(findFalseStarts([]), []);
  assert.deepEqual(findFalseStarts(null), []);
  assert.deepEqual(findFalseStarts(undefined), []);
});

test("findFalseStarts: inputs are never mutated", () => {
  const words = Object.freeze([
    Object.freeze({ text: "we", s: 0, e: 100 }),
    Object.freeze({ text: "must", s: 150, e: 250 }),
    Object.freeze({ text: "we", s: 300, e: 400 }),
    Object.freeze({ text: "must", s: 450, e: 550 }),
  ]);
  const options = Object.freeze({ minWords: 2, maxGap: 48000 });
  const hits = findFalseStarts(words, options);
  assert.equal(hits.length, 1);
});
