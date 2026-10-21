// The clipboard preview's page state: which chip plays, its Play/Stop button and its
// progress meter's fill.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  previewButton,
  previewFraction,
  previewPlaying,
  previewStop,
} from "../clipboard-preview.js";

test("the chip's Stop ends only the preview while the timeline plays (it is mixed in)", () => {
  assert.equal(previewStop({ playing: true, clipboardPlaying: { id: "a", seq: 5 } }), "preview");
  // alone (the timeline is not playing): the transport's stop puts the playhead back
  assert.equal(previewStop({ playing: false, clipboardPlaying: { id: "a", seq: 5 } }), "transport");
});

test("the fraction is the heard frame over the excerpt's length, held in 0..1", () => {
  assert.equal(previewFraction(0, 48000), 0);
  assert.equal(previewFraction(12000, 48000), 0.25);
  assert.equal(previewFraction(48000, 48000), 1);
  assert.equal(previewFraction(60000, 48000), 1);
  assert.equal(previewFraction(-5, 48000), 0);
  assert.equal(previewFraction(100, 0), 0);
  assert.equal(previewFraction(100, null), 0);
  assert.equal(previewFraction(Number.NaN, 100), 0);
});

test("idle, playing, stopped by the user", () => {
  let playing = null;
  playing = previewPlaying(playing, { type: "start", id: "a", seq: 5 });
  assert.deepEqual(playing, { id: "a", seq: 5 });
  playing = previewPlaying(playing, { type: "stop" });
  assert.equal(playing, null);
});

test("starting another chip switches over; the old one's end does not stop the new", () => {
  let playing = previewPlaying(null, { type: "start", id: "a", seq: 5 });
  playing = previewPlaying(playing, { type: "start", id: "b", seq: 8 });
  assert.deepEqual(playing, { id: "b", seq: 8 });
  // "a" ended at version 7, before "b" started at 8: dropped
  assert.deepEqual(previewPlaying(playing, { type: "ended", seq: 7 }), { id: "b", seq: 8 });
});

test("a preview that finishes by itself returns to idle", () => {
  const playing = previewPlaying(null, { type: "start", id: "a", seq: 5 });
  assert.equal(previewPlaying(playing, { type: "ended", seq: 7 }), null);
  assert.equal(previewPlaying(null, { type: "ended", seq: 7 }), null);
  // without versions an end always counts
  assert.equal(previewPlaying({ id: "a", seq: null }, { type: "ended", seq: 3 }), null);
});

test("only the playing chip shows Stop", () => {
  const playing = { id: "a", seq: 1 };
  assert.deepEqual(previewButton(playing, "a"), {
    playing: true,
    icon: "stop",
    labelKey: "ui.clipboard.preview_stop",
  });
  assert.deepEqual(previewButton(playing, "b"), {
    playing: false,
    icon: "play",
    labelKey: "ui.clipboard.preview",
  });
  assert.equal(previewButton(null, "a").playing, false);
});
