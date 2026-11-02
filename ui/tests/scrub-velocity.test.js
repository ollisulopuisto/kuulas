import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRulerScrub, dragVelocity } from "../scrub-velocity.js";

describe("dragVelocity", () => {
  test("forward drag: one second of programme in a second is 1x", () => {
    const v = dragVelocity(
      [
        { t: 0, frame: 0 },
        { t: 50, frame: 2400 },
      ],
      48000,
    );
    assert.equal(v, 1);
  });
  test("backward is negative", () => {
    const v = dragVelocity(
      [
        { t: 0, frame: 96000 },
        { t: 40, frame: 96000 - 4 * 1920 },
      ],
      48000,
    );
    assert.ok(Math.abs(v + 4) < 1e-9);
  });
  test("old samples do not count, one sample is no speed", () => {
    const old = { t: 0, frame: 0 };
    const now = { t: 500, frame: 48000 };
    assert.equal(dragVelocity([old, now], 48000), 0);
    assert.equal(dragVelocity([now], 48000), 0);
    assert.equal(dragVelocity([], 48000), 0);
  });
});

describe("createRulerScrub", () => {
  const make = () => {
    const sent = [];
    const scrub = createRulerScrub({ send: (f, v) => sent.push([f, v]), rate: 48000 });
    return { sent, scrub };
  };
  test("the press sends nothing; a drag sends bursts at the drag's velocity", () => {
    const { sent, scrub } = make();
    scrub.down(48000, 0);
    assert.deepEqual(sent, []);
    assert.equal(scrub.move(48000 + 2400, 40), true); // 0.05 s in 0.04 s: 1.25x
    assert.equal(sent.length, 1);
    assert.equal(sent[0][0], 50400);
    assert.ok(Math.abs(sent[0][1] - 1.25) < 1e-9);
    assert.equal(scrub.move(48000 - 4800, 80), true); // back past the start: negative
    assert.ok(sent[1][1] < 0);
  });
  test("moves too soon after a burst, or to the same frame, are skipped", () => {
    const { sent, scrub } = make();
    scrub.down(0, 0);
    scrub.move(1000, 40);
    assert.equal(scrub.move(2000, 50), false); // 10 ms later
    assert.equal(scrub.move(1000, 100), false); // the frame already sent
    assert.equal(sent.length, 1);
  });
  test("after release nothing is sent", () => {
    const { sent, scrub } = make();
    scrub.down(0, 0);
    scrub.up();
    assert.equal(scrub.active, false);
    assert.equal(scrub.move(5000, 100), false);
    assert.deepEqual(sent, []);
  });
});
