import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createPreviewPlayer, previewSegments } from "../candidates-preview.js";

describe("previewSegments: what is played, in order", () => {
  test("before the skip, then after it", () => {
    assert.deepEqual(previewSegments({ from: 100, to: 900, skip: [[300, 500]] }), [
      { at: 100, until: 300 },
      { at: 500, until: 900 },
    ]);
  });
  test("two skipped pieces make three segments", () => {
    assert.deepEqual(
      previewSegments({
        from: 0,
        to: 1000,
        skip: [
          [100, 200],
          [400, 600],
        ],
      }),
      [
        { at: 0, until: 100 },
        { at: 200, until: 400 },
        { at: 600, until: 1000 },
      ],
    );
  });
  test("a skip at the very start or end leaves no empty segment", () => {
    assert.deepEqual(previewSegments({ from: 0, to: 500, skip: [[0, 200]] }), [
      { at: 200, until: 500 },
    ]);
    assert.deepEqual(previewSegments({ from: 0, to: 500, skip: [[300, 500]] }), [
      { at: 0, until: 300 },
    ]);
  });
  test("no skip: nothing to jump, the whole range as one segment", () => {
    assert.deepEqual(previewSegments({ from: 5, to: 50, skip: [] }), [{ at: 5, until: 50 }]);
  });
});

function setup() {
  const played = [];
  const timers = [];
  const player = createPreviewPlayer({
    rate: 100,
    playSegment: (at, until) => {
      played.push([at, until]);
      return Promise.resolve();
    },
    stop: () => played.push("stop"),
    schedule: (fn, ms) => {
      timers.push({ fn, ms, live: true });
      return timers.length - 1;
    },
    cancel: (id) => {
      timers[id].live = false;
    },
  });
  return { player, played, timers };
}

describe("the jump preview", () => {
  test("plays the first segment and waits its length before the next", async () => {
    const { player, played, timers } = setup();
    await player.start({ from: 0, to: 1000, skip: [[200, 500]] });
    assert.deepEqual(played, [[0, 200]]);
    assert.equal(timers.length, 1);
    assert.ok(timers[0].ms >= 2000 && timers[0].ms <= 2200, `waits about 2 s: ${timers[0].ms}`);
    await timers[0].fn();
    assert.deepEqual(played, [
      [0, 200],
      [500, 1000],
    ]);
    assert.equal(player.active(), false, "the last segment needs no timer: the engine stops there");
  });

  test("cancel stops the chain: the second segment is never started", async () => {
    const { player, played, timers } = setup();
    await player.start({ from: 0, to: 1000, skip: [[200, 500]] });
    player.cancel();
    assert.equal(timers[0].live, false);
    assert.equal(player.active(), false);
    await timers[0].fn?.();
    assert.deepEqual(played, [[0, 200]], "a timer that fires late does nothing");
  });

  test("starting again cancels the one before", async () => {
    const { player, played, timers } = setup();
    await player.start({ from: 0, to: 1000, skip: [[200, 500]] });
    await player.start({ from: 0, to: 400, skip: [[100, 200]] });
    assert.equal(timers[0].live, false);
    assert.deepEqual(played.at(-1), [0, 100]);
  });

  test("nothing to preview: nothing is played", async () => {
    const { player, played } = setup();
    assert.equal(await player.start(null), false);
    assert.deepEqual(played, []);
  });
});
