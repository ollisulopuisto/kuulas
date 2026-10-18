import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  aboutSeconds,
  countWords,
  estimateFrames,
  estimatePreview,
  fitText,
  newPlaceholderId,
  placeholderAt,
  placeholderLabel,
  selectedPlaceholder,
  targetTrack,
} from "../placeholders-model.js";

const RATE = 48000;
const measure = (text) => text.length * 6;

describe("the estimate", () => {
  test("counts words as the server does", () => {
    assert.equal(countWords("Päivää, kaikki!"), 2);
    assert.equal(countWords("e-mail don't 3.5"), 3);
    assert.equal(countWords("  "), 0);
    assert.equal(countWords(null), 0);
  });

  test("23 words at 2.3 a second is ten seconds, one word is a second, none is zero", () => {
    const text = Array.from({ length: 23 }, () => "word").join(" ");
    assert.equal(estimateFrames(text, RATE), 480_000);
    assert.equal(estimateFrames("Hello", RATE), RATE);
    assert.equal(estimateFrames("", RATE), 0);
  });

  test("the preview says words and whole seconds", () => {
    assert.deepEqual(estimatePreview("one two three four five six seven eight nine ten", RATE), {
      words: 10,
      seconds: 4,
    });
    assert.deepEqual(estimatePreview("", RATE), { words: 0, seconds: 0 });
    assert.equal(aboutSeconds(1, RATE), 1);
  });
});

describe("hit testing", () => {
  const list = [
    { id: "a", track: "t1", start: 100, length: 50 },
    { id: "b", track: "t2", start: 100, length: 50 },
  ];
  test("the placeholder on that track under the frame", () => {
    assert.equal(placeholderAt(list, "t1", 120).id, "a");
    assert.equal(placeholderAt(list, "t2", 100).id, "b");
  });
  test("end is exclusive; other tracks and gaps miss", () => {
    assert.equal(placeholderAt(list, "t1", 150), null);
    assert.equal(placeholderAt(list, "t1", 99), null);
    assert.equal(placeholderAt(list, "t3", 120), null);
    assert.equal(placeholderAt(undefined, "t1", 120), null);
  });
});

describe("selection and target", () => {
  test("selectedPlaceholder finds the picked one", () => {
    const state = { project: { placeholders: [{ id: "a" }] }, placeholderSelected: "a" };
    assert.equal(selectedPlaceholder(state).id, "a");
    assert.equal(selectedPlaceholder({ ...state, placeholderSelected: "zz" }), null);
    assert.equal(selectedPlaceholder({ project: {} }), null);
  });
  test("the new one goes on the current track, else the first", () => {
    const project = { tracks: [{ id: "t1" }, { id: "t2" }] };
    assert.equal(targetTrack({ project, focusTrack: "t2" }), "t2");
    assert.equal(targetTrack({ project, focusTrack: "gone" }), "t1");
    assert.equal(targetTrack({ project: { tracks: [] } }), null);
  });
  test("ids look like the server's", () => {
    assert.match(
      newPlaceholderId(() => 0.5),
      /^h[0-9a-f]{10}$/,
    );
  });
});

describe("label fit", () => {
  test("clips with an ellipsis", () => {
    assert.equal(fitText("abcdefghij", 40, measure), "abcde…");
  });
  test("whole text when it fits, nothing when there is no room", () => {
    assert.equal(fitText("abc", 100, measure), "abc");
    assert.equal(fitText("abc", 0, measure), "");
    assert.equal(fitText("abcdef", 5, measure), "");
  });
  test("wide: script and estimate; medium: script only, clipped; narrow: nothing", () => {
    const base = { text: "Intro line", estimate: "about 6 s", measure };
    const wide = placeholderLabel({ ...base, width: 400 });
    assert.equal(wide.script, "“Intro line”");
    assert.equal(wide.estimate, "  about 6 s");
    const medium = placeholderLabel({ ...base, width: 70 });
    assert.equal(medium.estimate, "");
    assert.ok(measure(medium.script) <= 58);
    assert.ok(medium.script.endsWith("…"));
    assert.deepEqual(placeholderLabel({ ...base, width: 30 }), { script: "", estimate: "" });
  });
});
