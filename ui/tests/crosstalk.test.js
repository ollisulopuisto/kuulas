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
});
