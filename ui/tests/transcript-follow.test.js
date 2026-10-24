import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { transcriptFollowStep } from "../transcript-follow.js";

describe("transcript follow unlock", () => {
  test("manual scrolling while playing unlocks transcript follow", () => {
    assert.deepEqual(
      transcriptFollowStep({ paused: false, playing: true }, { type: "manual-scroll" }),
      { paused: true },
    );
  });

  test("playback ticks and the playhead returning to view do not relock follow", () => {
    const unlocked = { paused: true, playing: true };
    for (const type of ["tick", "playhead-in-view"]) {
      assert.deepEqual(transcriptFollowStep(unlocked, { type }), { paused: true });
    }
  });

  test("the Follow control explicitly relocks; stopped scrolling has no effect", () => {
    assert.deepEqual(transcriptFollowStep({ paused: true, playing: true }, { type: "follow" }), {
      paused: false,
    });
    assert.deepEqual(
      transcriptFollowStep({ paused: false, playing: false }, { type: "manual-scroll" }),
      { paused: false },
    );
  });
});
