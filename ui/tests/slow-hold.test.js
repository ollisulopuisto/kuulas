import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  createSlowHold,
  DEFAULT_SLOW,
  normaliseSlow,
  SLOW_SPEEDS,
  slowSpeed,
} from "../slow-hold.js";

function rig({ canStart = true } = {}) {
  const log = [];
  const hold = createSlowHold({
    canStart: () => canStart,
    start: (direction) => log.push(["start", direction]),
    stop: () => log.push(["stop"]),
  });
  return { hold, log };
}

describe("slow speeds", () => {
  test("0.25, 0.5 and 0.75, default 0.5", () => {
    assert.deepEqual(SLOW_SPEEDS, [0.25, 0.5, 0.75]);
    assert.equal(DEFAULT_SLOW, 0.5);
  });
  test("the direction sets the sign", () => {
    assert.equal(slowSpeed("l", 0.75), 0.75);
    assert.equal(slowSpeed("j", 0.25), -0.25);
  });
  test("anything else becomes the default", () => {
    assert.equal(normaliseSlow("0.6"), 0.5);
    assert.equal(normaliseSlow(null), 0.5);
    assert.equal(normaliseSlow("0.75"), 0.75);
    assert.equal(slowSpeed("l", 9), 0.5);
  });
  test("an unknown direction throws", () => assert.throws(() => slowSpeed("k", 0.5)));
});

describe("hold-to-play state machine", () => {
  test("keydown starts, keyup stops", () => {
    const { hold, log } = rig();
    hold.press("l", "KeyL");
    assert.equal(hold.isHeld(), true);
    hold.release("KeyL");
    assert.equal(hold.isHeld(), false);
    assert.deepEqual(log, [["start", "l"], ["stop"]]);
  });
  test("auto-repeat keydowns do not restart it", () => {
    const { hold, log } = rig();
    hold.press("j", "KeyJ");
    hold.press("j", "KeyJ");
    hold.press("j", "KeyJ");
    assert.deepEqual(log, [["start", "j"]]);
  });
  test("the other direction while held is ignored", () => {
    const { hold, log } = rig();
    hold.press("j", "KeyJ");
    hold.press("l", "KeyL");
    hold.release("KeyL");
    assert.deepEqual(log, [["start", "j"]]);
    hold.release("KeyJ");
    assert.deepEqual(log, [["start", "j"], ["stop"]]);
  });
  test("releasing Shift first also stops", () => {
    const { hold, log } = rig();
    hold.press("l", "KeyL");
    hold.release("ShiftLeft");
    assert.deepEqual(log, [["start", "l"], ["stop"]]);
  });
  test("an unrelated keyup does nothing", () => {
    const { hold, log } = rig();
    hold.press("l", "KeyL");
    hold.release("KeyA");
    assert.deepEqual(log, [["start", "l"]]);
  });
  test("cancel (blur, focus loss, Esc, another command) stops once", () => {
    const { hold, log } = rig();
    hold.press("l", "KeyL");
    hold.cancel();
    hold.cancel();
    hold.release("KeyL");
    assert.deepEqual(log, [["start", "l"], ["stop"]]);
  });
  test("cancel and release with nothing held do nothing", () => {
    const { hold, log } = rig();
    hold.cancel();
    hold.release("KeyL");
    assert.deepEqual(log, []);
  });
  test("while normal playback runs the press is ignored", () => {
    const { hold, log } = rig({ canStart: false });
    hold.press("l", "KeyL");
    hold.release("KeyL");
    assert.deepEqual(log, []);
    assert.equal(hold.isHeld(), false);
  });
  test("it can be held again after a release", () => {
    const { hold, log } = rig();
    hold.press("l", "KeyL");
    hold.release("KeyL");
    hold.press("j", "KeyJ");
    assert.deepEqual(log, [["start", "l"], ["stop"], ["start", "j"]]);
  });
});
