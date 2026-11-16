import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { followWord, transcriptFollowStep, transcriptPlaybackStep } from "../transcript-follow.js";

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

  test("repeated playing anchors do not relock a manually unlocked transcript", () => {
    const first = transcriptPlaybackStep({ paused: true, wasPlaying: true }, true);
    assert.deepEqual(first, { paused: true, wasPlaying: true });
    assert.deepEqual(transcriptPlaybackStep(first, true), first);
  });

  test("the Follow control explicitly relocks; scrolling always unlocks", () => {
    assert.deepEqual(transcriptFollowStep({ paused: true, playing: true }, { type: "follow" }), {
      paused: false,
    });
    assert.deepEqual(
      transcriptFollowStep({ paused: false, playing: false }, { type: "manual-scroll" }),
      { paused: true },
    );
  });
});

describe("which word the transcript scrolls to", () => {
  test("a moved playhead reveals its word when playback is stopped, even after a manual scroll", () => {
    assert.equal(followWord({ playing: false, paused: true, at: 7, before: 6 }), 7);
  });

  test("while playing, a manual scroll keeps the transcript where the user put it", () => {
    assert.equal(followWord({ playing: true, paused: true, at: 7, before: 6 }), -1);
  });

  test("in a pause between words it follows to the last word started, playing or not", () => {
    assert.equal(followWord({ playing: true, paused: false, at: -1, before: 6 }), 6);
    assert.equal(followWord({ playing: false, paused: false, at: -1, before: 6 }), 6);
  });

  test("with no words there is nothing to reveal", () => {
    assert.equal(followWord({ playing: false, paused: false, at: -1, before: -1 }), -1);
  });
});
