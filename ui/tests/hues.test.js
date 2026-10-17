import assert from "node:assert/strict";
import { test } from "node:test";
import { MUSIC_HUE, SPEAKER_HUES, trackHues } from "../paint.js";

const track = (id, kind = "speech", speaker = "") => ({ id, kind, speaker, clips: [] });

test("speech tracks take the speaker hues in order, music its own", () => {
  const hues = trackHues({
    tracks: [track("a"), track("m", "music"), track("b"), track("z", "speech-mix")],
  });
  assert.equal(hues.get("a"), 0);
  assert.equal(hues.get("m"), MUSIC_HUE);
  // Music does not use up a speaker hue: the next speech track is 1, not 2.
  assert.equal(hues.get("b"), 1);
  assert.equal(hues.get("z"), 2);
});

test("tracks of the same speaker share one hue", () => {
  const hues = trackHues({
    tracks: [
      track("a1", "speech", "p-anna"),
      track("v", "speech", "p-ville"),
      track("a2", "speech", "p-anna"),
    ],
  });
  assert.equal(hues.get("a1"), hues.get("a2"));
  assert.equal(hues.get("v"), 1);
});

test("hues cycle after the last speaker hue", () => {
  const tracks = Array.from({ length: SPEAKER_HUES + 1 }, (_, i) => track(`t${i}`));
  assert.equal(trackHues({ tracks }).get(`t${SPEAKER_HUES}`), 0);
});

test("no project gives an empty map", () => {
  assert.equal(trackHues(null).size, 0);
});
