// What a transcript cut also removes (owner, 2026-10-18): words of other
// speakers inside the cut stretch, and audio on the other tracks of the scope.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { cutPreview } from "../crosstalk.js";

const w = (track, start, end, text) => ({ track, start, end, text });
const words = [
  w("anna", 0, 10, "Mut"), // 0
  w("anna", 10, 20, "niinku"), // 1
  w("anna", 20, 30, "öö"), // 2
  w("anna", 30, 40, "siis"), // 3
  w("ville", 22, 28, "joo"), // 4: inside the stretch
  w("ville", 38, 50, "mm"), // 5: overlaps the end
  w("ville", 60, 70, "later"), // 6: outside
];

describe("cutPreview", () => {
  test("the stretch is the selected words' span; overlapping words of others are listed", () => {
    const preview = cutPreview(words, [1, 2, 3], ["anna", "ville", "pekka"]);
    assert.deepEqual(preview.range, [10, 40]);
    assert.deepEqual(preview.alsoWords, [4, 5]);
    assert.deepEqual(
      preview.tracks.map((t) => [t.track, t.words.length]),
      [
        ["ville", 2],
        ["pekka", 0],
      ],
    );
    assert.equal(preview.nothingElse, false);
  });

  test("a track with no words still loses the stretch of audio", () => {
    const preview = cutPreview(words, [1], ["anna", "pekka"]);
    assert.deepEqual(preview.tracks, [{ track: "pekka", words: [], seconds: 10 }]);
  });

  test("nothing else when no other track is in scope", () => {
    const preview = cutPreview(words, [0], ["anna"]);
    assert.equal(preview.nothingElse, true);
    assert.deepEqual(preview.tracks, []);
  });

  test("seconds are the stretch length at the given rate", () => {
    const preview = cutPreview(words, [1, 2, 3], ["anna", "ville"], 10);
    assert.equal(preview.tracks[0].seconds, 3);
  });

  test("no selection, no preview", () => {
    assert.equal(cutPreview(words, [], ["anna"]), null);
  });

  test("multi-track stretch: alsoWords grouped per non-owner track in scope order", () => {
    const many = [];
    for (let t = 0; t < 4; t += 1) {
      const track = `spk${t}`;
      let s = t * 2000;
      for (let k = 0; k < 30; k += 1) {
        many.push({ track, start: s, end: s + 400, text: `w${k}` });
        s += 420;
      }
    }
    // spk1 words 5..9 (indices 35..39) are selected; stretch covers spk0 and spk2 words inside it.
    const preview = cutPreview(many, [35, 36, 37, 38, 39], ["spk0", "spk1", "spk2", "spk3"]);
    assert.deepEqual(preview.range, [many[35].start, many[39].end]);
    // alsoWords are non-selected, non-owner words overlapping the stretch, in index order.
    const expectedAlso = [];
    for (let i = 0; i < many.length; i += 1) {
      if ([35, 36, 37, 38, 39].includes(i)) continue;
      if (many[i].track === "spk1") continue;
      if (many[i].start < many[39].end && many[i].end > many[35].start) expectedAlso.push(i);
    }
    assert.deepEqual(preview.alsoWords, expectedAlso);
    // tracks appear in scope order, owners skipped, each with its own words.
    assert.deepEqual(
      preview.tracks.map((t) => [t.track, t.words.length]),
      [
        ["spk0", expectedAlso.filter((i) => many[i].track === "spk0").length],
        ["spk2", expectedAlso.filter((i) => many[i].track === "spk2").length],
        ["spk3", expectedAlso.filter((i) => many[i].track === "spk3").length],
      ],
    );
    assert.equal(preview.nothingElse, false);
  });

  test("nothing else when scope has only the owner track", () => {
    const preview = cutPreview(words, [1], ["anna"]);
    assert.equal(preview.nothingElse, true);
    assert.deepEqual(preview.tracks, []);
  });
});
