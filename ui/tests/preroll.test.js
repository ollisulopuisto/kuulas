import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  ARM_KEEPALIVE_MS,
  armedNotice,
  armRequest,
  DEFAULT_PREROLL_S,
  nextPreroll,
  PREROLL_CHOICES,
  prerollChoice,
  prerollLabel,
} from "../preroll.js";

const t = (key, params = {}) => `${key}${JSON.stringify(params)}`;

describe("the preference", () => {
  test("a minute is the default; 0 switches it off; anything unknown falls back", () => {
    assert.equal(DEFAULT_PREROLL_S, 60);
    assert.equal(prerollChoice(null), 60);
    assert.equal(prerollChoice("nonsense"), 60);
    assert.equal(prerollChoice("45"), 60);
    assert.equal(prerollChoice("0"), 0);
    assert.equal(prerollChoice(0), 0);
    assert.equal(prerollChoice("120"), 120);
  });
  test("the menu item cycles through the choices and wraps", () => {
    assert.deepEqual(PREROLL_CHOICES, [0, 10, 30, 60, 120]);
    assert.equal(nextPreroll(0), 10);
    assert.equal(nextPreroll(10), 30);
    assert.equal(nextPreroll(30), 60);
    assert.equal(nextPreroll(60), 120);
    assert.equal(nextPreroll(120), 0);
    assert.equal(nextPreroll("bad"), 120); // unknown counts as the default, 60
  });
  test("labels say off or seconds", () => {
    assert.equal(prerollLabel(0, t), "ui.record.preroll.off{}");
    assert.equal(prerollLabel(30, t), 'ui.record.preroll.seconds{"seconds":30}');
  });
});

describe("the arm request", () => {
  test("is the input, the channel and the seconds", () => {
    assert.deepEqual(
      armRequest({ device: { index: 2, name: "Mic", channels: 2 }, channel: "2", seconds: 30 }),
      { device: { index: 2, name: "Mic" }, channel: 2, preroll_s: 30 },
    );
    assert.deepEqual(armRequest({ device: null, channel: 0, seconds: 60 }), {
      device: null,
      channel: 1,
      preroll_s: 60,
    });
  });
  test("keeps the recorder armed well inside its time-to-live of two minutes", () => {
    assert.ok(ARM_KEEPALIVE_MS <= 30000);
    assert.ok(ARM_KEEPALIVE_MS >= 5000);
  });
});

describe("what the view says about listening", () => {
  test("nothing listens when pre-roll is off", () => {
    assert.equal(armedNotice({ armed: false }, 0, t), "ui.record.armed_off{}");
    // even a stale armed status: with 0 selected the view disarms, so it says off
    assert.equal(armedNotice({ armed: true, preroll_s: 30 }, 0, t), "ui.record.armed_off{}");
  });
  test("unmistakable once the recorder is listening", () => {
    assert.equal(
      armedNotice({ armed: true, preroll_s: 30 }, 30, t),
      'ui.record.armed{"seconds":30}',
    );
  });
  test("a moment of opening the input before it listens", () => {
    assert.equal(armedNotice({ armed: false }, 30, t), "ui.record.armed_starting{}");
    assert.equal(armedNotice(null, 30, t), "ui.record.armed_starting{}");
  });
});
