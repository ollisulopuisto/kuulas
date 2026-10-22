import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  alsoRemovedIndices,
  buildParagraphs,
  collateralBand,
  cutRange,
  cutWordsPlan,
  DEFAULT_PAUSE_CHOICE,
  deleteSpan,
  deleteWordsPlan,
  dragSelection,
  estimateHeight,
  extendTo,
  moveCursor,
  mutedInputsKey,
  noSelection,
  offsetsOf,
  ownerTracks,
  PAUSE_CHOICES,
  paragraphOf,
  pauseChoiceId,
  pauseMarkers,
  pauseSecondsOf,
  placeCursor,
  selectedIndices,
  selectionBounds,
  selectionFrames,
  selectWord,
  shouldLoadWords,
  speakerName,
  summaryParts,
  transcribedMedia,
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
      { op: "mute_range", args: { start: 55, end: 210, track_ids: ["a"] } },
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

describe("cutRange", () => {
  const w = (s, e) => ({ s, e });
  const words = [w(0, 50), w(60, 120), w(200, 260), w(300, 350)];
  test("each side goes to the middle of the pause", () => {
    assert.deepEqual(cutRange(words, [1, 2]), { start: 55, end: 280 });
  });
  test("at the ends of the programme it cuts to the word", () => {
    assert.deepEqual(cutRange(words, [0]), { start: 0, end: 55 });
    assert.deepEqual(cutRange(words, [3]), { start: 280, end: 350 });
  });
  test("nothing selected: null", () => {
    assert.equal(cutRange(words, []), null);
  });
});

describe("pause markers", () => {
  // rate 100: frames / 100 = seconds
  const build = (words, pauseSeconds) => ({
    words,
    paragraphs: buildParagraphs(words, { rate: RATE, pauseSeconds }),
  });

  test("a pause split gets a marker with its range and length", () => {
    const { words, paragraphs } = build([word("a", 0, 100), word("b", 740, 800)], 3);
    assert.equal(paragraphs.length, 2);
    const markers = pauseMarkers(words, paragraphs, RATE);
    assert.deepEqual([...markers.keys()], [1]);
    assert.deepEqual(markers.get(1), { start: 100, end: 740, seconds: 6.4 });
  });

  test("no marker for a speaker change, even after a long gap", () => {
    const { words, paragraphs } = build([word("a", 0, 100), word("b", 900, 950, "b")], 3);
    assert.equal(paragraphs.length, 2);
    assert.equal(pauseMarkers(words, paragraphs, RATE).size, 0);
  });

  test("no marker under 1 s, even when the threshold splits there", () => {
    const { words, paragraphs } = build([word("a", 0, 100), word("b", 190, 250)], 0.5);
    assert.equal(paragraphs.length, 2);
    assert.equal(pauseMarkers(words, paragraphs, RATE).size, 0);
  });

  test("exactly 1 s gets a marker; the first paragraph never does", () => {
    const { words, paragraphs } = build([word("a", 0, 100), word("b", 200, 250)], 0.5);
    const markers = pauseMarkers(words, paragraphs, RATE);
    assert.deepEqual([...markers.keys()], [1]);
    assert.equal(markers.get(1).seconds, 1);
  });

  test("a gap inside a paragraph (below the threshold) has no marker", () => {
    const { words, paragraphs } = build([word("a", 0, 100), word("b", 400, 450)], 3);
    assert.equal(paragraphs.length, 1);
    assert.equal(pauseMarkers(words, paragraphs, RATE).size, 0);
  });
});

describe("pause threshold choices", () => {
  test("four choices; 3 s is the default; never is Infinity", () => {
    assert.deepEqual(
      PAUSE_CHOICES.map((c) => c.id),
      ["1_5", "3", "6", "never"],
    );
    assert.equal(DEFAULT_PAUSE_CHOICE, "3");
    assert.equal(pauseSecondsOf("1_5"), 1.5);
    assert.equal(pauseSecondsOf("3"), 3);
    assert.equal(pauseSecondsOf("6"), 6);
    assert.equal(pauseSecondsOf("never"), Number.POSITIVE_INFINITY);
  });

  test("an unknown or missing stored value falls back to the default", () => {
    assert.equal(pauseChoiceId("6"), "6");
    assert.equal(pauseChoiceId("never"), "never");
    assert.equal(pauseChoiceId(null), "3");
    assert.equal(pauseChoiceId("2"), "3");
    assert.equal(pauseSecondsOf("bogus"), 3);
  });

  test("never keeps a long pause inside one paragraph", () => {
    const words = [word("a", 0, 100), word("b", 100000, 100050)];
    const paragraphs = buildParagraphs(words, {
      rate: RATE,
      pauseSeconds: pauseSecondsOf("never"),
    });
    assert.equal(paragraphs.length, 1);
  });
});

describe("when the words are fetched again (muted flags come from the server)", () => {
  const project = (track = {}, bus = {}, clip = {}) => ({
    tracks: [
      {
        id: "t1",
        mute: false,
        solo: false,
        bus: "b1",
        clips: [{ id: "c1", muted: false, ...clip }],
        ...track,
      },
      { id: "t2", mute: false, solo: false, clips: [] },
    ],
    buses: [{ id: "b1", mute: false, ...bus }],
  });

  test("the key changes with mute, solo, bus mute and clip mute, and with nothing else", () => {
    const base = mutedInputsKey(project());
    assert.notEqual(mutedInputsKey(project({ mute: true })), base);
    assert.notEqual(mutedInputsKey(project({ solo: true })), base);
    assert.notEqual(mutedInputsKey(project({}, { mute: true })), base);
    assert.notEqual(mutedInputsKey(project({}, {}, { muted: true })), base);
    assert.equal(mutedInputsKey(project({ gain: 3, name: "x" })), base);
    assert.equal(mutedInputsKey(null), "");
  });

  const idle = { head: "h1", key: "K0", fetchedHead: "h1", fetchedKey: "K0", fetching: false };

  test("nothing changed: no fetch", () => {
    assert.equal(shouldLoadWords(idle), false);
  });

  test("a new head, or a new key under the same head, fetches", () => {
    assert.equal(shouldLoadWords({ ...idle, head: "h2" }), true);
    assert.equal(shouldLoadWords({ ...idle, key: "K1" }), true);
  });

  test("mute then unmute: the server merges both into one step (same head), the key still differs from the fetch", () => {
    // M1 answered (head h1, key K1) and fetched; M2 coalesces into h1: head unchanged, key back to K0.
    const afterFetch = { ...idle, head: "h1", fetchedHead: "h1", fetchedKey: "K1", key: "K0" };
    assert.equal(shouldLoadWords(afterFetch), true);
  });

  test("a fetch in flight waits, and is repeated when the key moved meanwhile", () => {
    assert.equal(shouldLoadWords({ ...idle, key: "K1", fetching: true }), false);
    // It finished having started for K0; the state is K1 now.
    assert.equal(shouldLoadWords({ ...idle, key: "K1", fetching: false }), true);
  });

  test("no head yet: nothing to fetch; force always fetches", () => {
    assert.equal(shouldLoadWords({ ...idle, head: null, key: "K1" }), false);
    assert.equal(shouldLoadWords({ ...idle, force: true }), true);
    assert.equal(shouldLoadWords({ ...idle, force: true, fetching: true }), false);
  });
});

describe("the selection as in and out marks", () => {
  const words = [
    { s: 100, e: 200 },
    { s: 210, e: 300 },
    { s: 310, e: 400 },
    { s: 250, e: 520 }, // another speaker, overlapping
  ];
  test("a selected run gives its first start and last end", () => {
    assert.deepEqual(selectionFrames(words, { anchor: 1, cursor: 2 }), {
      inPoint: 210,
      outPoint: 400,
    });
  });
  test("the direction does not matter, and overlaps widen the span", () => {
    assert.deepEqual(selectionFrames(words, { anchor: 3, cursor: 1 }), {
      inPoint: 210,
      outPoint: 520,
    });
  });
  test("one double-clicked word is a range too", () => {
    assert.deepEqual(selectionFrames(words, { anchor: 0, cursor: 0 }), {
      inPoint: 100,
      outPoint: 200,
    });
  });
  test("a bare cursor, no selection or stale indices give nothing", () => {
    assert.equal(selectionFrames(words, { anchor: null, cursor: 1 }), null);
    assert.equal(selectionFrames(words, null), null);
    assert.equal(selectionFrames(words, { anchor: 2, cursor: 9 }), null);
    assert.equal(selectionFrames([], { anchor: 0, cursor: 0 }), null);
  });
});

describe("transcribedMedia", () => {
  test("the server's list counts even when every word of a recording is muted", () => {
    assert.deepEqual(transcribedMedia({ transcribed: ["m1", "m2"] }, []), ["m1", "m2"]);
  });
  test("words add their recordings, once each", () => {
    const words = [{ media: "m2" }, { media: "m3" }, { media: "m3" }];
    assert.deepEqual(transcribedMedia({ transcribed: ["m1", "m2"] }, words), ["m1", "m2", "m3"]);
  });
  test("nothing known is an empty list", () => {
    assert.deepEqual(transcribedMedia({}, []), []);
  });
});
