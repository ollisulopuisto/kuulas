import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  alsoRemovedIndices,
  buildParagraphs,
  collateralBand,
  cutWordsPlan,
  deleteSpan,
  deleteWordsPlan,
  dragSelection,
  estimateHeight,
  extendTo,
  moveCursor,
  noSelection,
  offsetsOf,
  ownerTracks,
  paragraphOf,
  placeCursor,
  selectedIndices,
  selectionBounds,
  selectWord,
  speakerName,
  summaryParts,
  visibleRange,
  wordAtTime,
  wordBefore,
  wordRefs,
} from "../transcript-model.js";

const RATE = 100;
const word = (w, s, e, track = "a", extra = {}) => ({
  w,
  s,
  e,
  track,
  clip: `c-${track}`,
  index: 0,
  ...extra,
});
const tracks = [
  { id: "a", name: "Anna.wav", speaker: "Anna" },
  { id: "b", name: "Ville.wav", speaker: "" },
];

describe("speaker names", () => {
  const byId = new Map(tracks.map((t) => [t.id, t]));
  test("a mapped person wins, then the track's speaker, then its name", () => {
    assert.equal(speakerName("a", byId, { p1: "Anna Virtanen" }, "p1"), "Anna Virtanen");
    assert.equal(speakerName("a", byId, {}, ""), "Anna");
    assert.equal(speakerName("b", byId, {}, "p9"), "Ville.wav");
    assert.equal(speakerName("zz", byId, {}, ""), "zz");
  });
});

describe("paragraphs", () => {
  const words = [
    word("hei", 0, 50),
    word("maailma", 60, 120),
    word("joo", 130, 160, "b"),
    word("taas", 170, 200),
    word("pitkä", 500, 560), // 3 s pause at 100 frames/s: a new paragraph
  ];
  const paragraphs = buildParagraphs(words, { rate: RATE, tracks });

  test("a speaker change and a long pause start a paragraph", () => {
    assert.deepEqual(
      paragraphs.map((p) => [p.first, p.last, p.track, p.name]),
      [
        [0, 1, "a", "Anna"],
        [2, 2, "b", "Ville.wav"],
        [3, 3, "a", "Anna"],
        [4, 4, "a", "Anna"],
      ],
    );
  });
  test("a pause of exactly 1.5 s does not split", () => {
    const two = [word("a", 0, 10), word("b", 160, 170)];
    assert.equal(buildParagraphs(two, { rate: RATE, tracks }).length, 1);
    const longer = [word("a", 0, 10), word("b", 161, 170)];
    assert.equal(buildParagraphs(longer, { rate: RATE, tracks }).length, 2);
  });
  test("a paragraph knows its time range and size", () => {
    assert.equal(paragraphs[0].start, 0);
    assert.equal(paragraphs[0].end, 120);
    assert.equal(paragraphs[0].chars, "hei ".length + "maailma ".length);
  });
  test("people names head the paragraph", () => {
    const named = [word("hei", 0, 50, "a", { person: "p1" })];
    const out = buildParagraphs(named, { rate: RATE, tracks, people: { p1: "Anna V." } });
    assert.equal(out[0].name, "Anna V.");
  });
  test("no words, no paragraphs", () => {
    assert.deepEqual(buildParagraphs([], { rate: RATE, tracks }), []);
  });
  test("paragraphOf finds the paragraph of a word", () => {
    assert.deepEqual(
      [0, 1, 2, 3, 4].map((i) => paragraphOf(paragraphs, i)),
      [0, 0, 1, 2, 3],
    );
    assert.equal(paragraphOf(paragraphs, 9), -1);
  });
});

describe("the word at a time", () => {
  const words = [
    word("a", 10, 30),
    word("b", 40, 90),
    word("c", 50, 60, "b"), // inside b
    word("d", 100, 120),
  ];
  test("finds the word being spoken", () => {
    assert.equal(wordAtTime(words, 10), 0);
    assert.equal(wordAtTime(words, 29), 0);
    assert.equal(wordAtTime(words, 45), 1);
    assert.equal(wordAtTime(words, 110), 3);
  });
  test("of two overlapping words, the later-starting one", () => {
    assert.equal(wordAtTime(words, 55), 2);
    assert.equal(wordAtTime(words, 70), 1); // c is over, b goes on
  });
  test("a pause and the ends have no word", () => {
    assert.equal(wordAtTime(words, 5), -1);
    assert.equal(wordAtTime(words, 35), -1);
    assert.equal(wordAtTime(words, 95), -1);
    assert.equal(wordAtTime(words, 500), -1);
    assert.equal(wordAtTime([], 5), -1);
  });
  test("wordBefore says where to scroll in a pause", () => {
    assert.equal(wordBefore(words, 35), 0);
    assert.equal(wordBefore(words, 5), 0);
    assert.equal(wordBefore(words, 500), 3);
    assert.equal(wordBefore([], 5), -1);
  });
  test("a nine-thousand-word hour is searched, not scanned", () => {
    const hour = Array.from({ length: 9000 }, (_, i) => word("w", i * 10, i * 10 + 8));
    assert.equal(wordAtTime(hour, 45_003), 4500);
  });
});

describe("which paragraphs to draw", () => {
  const heights = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100];
  const offsets = offsetsOf(heights);
  test("offsets are prefix sums", () => {
    assert.deepEqual(offsets.slice(0, 4), [0, 100, 200, 300]);
    assert.equal(offsets[10], 1000);
  });
  test("the window plus a margin, nothing more", () => {
    assert.deepEqual(visibleRange(offsets, 0, 250, 0), { from: 0, to: 3 });
    assert.deepEqual(visibleRange(offsets, 450, 200, 0), { from: 4, to: 7 });
    assert.deepEqual(visibleRange(offsets, 450, 200, 100), { from: 3, to: 8 });
  });
  test("clamped at both ends and for tiny or empty lists", () => {
    assert.deepEqual(visibleRange(offsets, 5000, 200, 100), { from: 9, to: 10 });
    assert.deepEqual(visibleRange(offsets, -500, 200, 0), { from: 0, to: 1 });
    assert.deepEqual(visibleRange([0], 0, 200, 100), { from: 0, to: 0 });
  });
  test("a long transcript draws a handful", () => {
    const many = offsetsOf(Array.from({ length: 2000 }, () => 80));
    const { from, to } = visibleRange(many, 80_000, 600, 400);
    assert.ok(to - from < 20, `${to - from} paragraphs`);
  });
  test("a height estimate grows with the text", () => {
    const sizes = { charsPerLine: 60, lineHeight: 30, gap: 20 };
    assert.equal(estimateHeight({ chars: 10 }, sizes), 50);
    assert.equal(estimateHeight({ chars: 61 }, sizes), 80);
    assert.equal(estimateHeight({ chars: 0 }, sizes), 50);
  });
});

describe("the word cursor and the selection", () => {
  const paragraphs = [
    { first: 0, last: 2 },
    { first: 3, last: 5 },
    { first: 6, last: 8 },
  ];
  const ctx = { count: 9, paragraphs };
  test("a plain cursor selects nothing", () => {
    assert.deepEqual(selectedIndices(placeCursor(4)), []);
    assert.deepEqual(selectedIndices(noSelection()), []);
    assert.equal(selectionBounds(placeCursor(4)), null);
  });
  test("shift extends from where the cursor was, both ways", () => {
    const right = extendTo(placeCursor(4), 6);
    assert.deepEqual(selectedIndices(right), [4, 5, 6]);
    const left = extendTo(placeCursor(4), 2);
    assert.deepEqual(selectedIndices(left), [2, 3, 4]);
    assert.deepEqual(selectionBounds(left), [2, 4]);
  });
  test("extending again keeps the anchor", () => {
    const sel = extendTo(extendTo(placeCursor(4), 6), 3);
    assert.deepEqual(selectedIndices(sel), [3, 4]);
  });
  test("shift with no cursor selects the word itself", () => {
    assert.deepEqual(selectedIndices(extendTo(noSelection(), 7)), [7]);
  });
  test("a drag against the reading direction selects the same words", () => {
    assert.deepEqual(selectedIndices(dragSelection(5, 2)), [2, 3, 4, 5]);
    assert.deepEqual(selectedIndices(dragSelection(2, 5)), [2, 3, 4, 5]);
  });
  test("a double click selects one word", () => {
    assert.deepEqual(selectedIndices(selectWord(3)), [3]);
  });
  test("arrows move word by word, stopping at the ends", () => {
    assert.equal(moveCursor(4, "ArrowRight", ctx), 5);
    assert.equal(moveCursor(4, "ArrowLeft", ctx), 3);
    assert.equal(moveCursor(8, "ArrowRight", ctx), 8);
    assert.equal(moveCursor(0, "ArrowLeft", ctx), 0);
    assert.equal(moveCursor(-1, "ArrowRight", ctx), 0);
  });
  test("up and down go by paragraph, Home and End to its ends", () => {
    assert.equal(moveCursor(4, "ArrowDown", ctx), 6);
    assert.equal(moveCursor(4, "ArrowUp", ctx), 0);
    assert.equal(moveCursor(7, "ArrowDown", ctx), 6);
    assert.equal(moveCursor(4, "Home", ctx), 3);
    assert.equal(moveCursor(4, "End", ctx), 5);
  });
  test("no words, no cursor", () => {
    assert.equal(moveCursor(-1, "ArrowRight", { count: 0, paragraphs: [] }), -1);
  });
});

describe("delete on this speaker only", () => {
  // Anna speaks 0-50, 60-120, 300-350; Ville overlaps 70-110.
  const words = [
    word("a1", 0, 50),
    word("a2", 60, 120),
    word("v1", 70, 110, "b"),
    word("a3", 300, 350),
  ];
  test("the span runs to the middle of the pause on Anna's own track", () => {
    assert.deepEqual(deleteSpan(words, [1], "a"), { start: 55, end: 210 });
  });
  test("at the ends of her speech it stops at the word", () => {
    assert.deepEqual(deleteSpan(words, [0], "a"), { start: 0, end: 55 });
    assert.deepEqual(deleteSpan(words, [3], "a"), { start: 210, end: 350 });
  });
  test("Ville's words do not shape Anna's span", () => {
    assert.deepEqual(deleteSpan(words, [1, 2], "a"), deleteSpan(words, [1], "a"));
    assert.equal(deleteSpan(words, [1], "b"), null);
  });
  test("the plan is one mute_range on that track alone, group editing off", () => {
    assert.deepEqual(deleteWordsPlan(words, [1]), [
      { op: "mute_range", args: { start: 55, end: 210, track_ids: ["a"], group_editing: false } },
    ]);
  });
  test("a selection over two speakers mutes each on their own track", () => {
    const plan = deleteWordsPlan(words, [1, 2]);
    assert.deepEqual(
      plan.map((e) => e.args.track_ids),
      [["a"], ["b"]],
    );
    assert.deepEqual(ownerTracks(words, [1, 2]), ["a", "b"]);
  });
  test("nothing selected, nothing sent", () => {
    assert.equal(deleteWordsPlan(words, []), null);
  });
});

describe("cut on all tracks", () => {
  test("the command carries the indices", () => {
    assert.deepEqual(cutWordsPlan([2, 3]), { name: "cut_words", args: { indices: [2, 3] } });
    assert.equal(cutWordsPlan([]), null);
  });
});

describe("the crosstalk preview", () => {
  const words = [
    { ...word("a", 0, 50), index: 0 },
    { ...word("v", 10, 40, "b"), index: 4 },
    { ...word("a", 60, 90), index: 1 },
  ];
  const preview = {
    span: [0, 50],
    other_words: [words[1]],
    audio: { b: [[10, 40]], m: [[0, 150]] },
  };
  test("word refs name track, clip and index", () => {
    assert.deepEqual(wordRefs(words, [0]), [{ track: "a", clip: "c-a", index: 0 }]);
  });
  test("the other speakers' words map back to array indices", () => {
    assert.deepEqual([...alsoRemovedIndices(words, preview)], [1]);
    assert.equal(alsoRemovedIndices(words, null).size, 0);
  });
  test("summary parts: words where there are words, audio seconds where not", () => {
    const parts = summaryParts(preview, { rate: 100, nameOf: (t) => `T-${t}` });
    assert.deepEqual(parts, [
      { track: "b", name: "T-b", words: 1, seconds: 0.3 },
      { track: "m", name: "T-m", words: 0, seconds: 1.5 },
    ]);
  });
  test("nothing else: no parts, no band", () => {
    const none = { span: [0, 50], other_words: [], audio: {} };
    assert.deepEqual(summaryParts(none, { rate: 100, nameOf: String }), []);
    assert.equal(collateralBand(none), null);
    assert.equal(collateralBand(null), null);
  });
  test("the band is the stretch and the affected tracks", () => {
    assert.deepEqual(collateralBand(preview), { range: [0, 50], tracks: ["b", "m"] });
  });
});
