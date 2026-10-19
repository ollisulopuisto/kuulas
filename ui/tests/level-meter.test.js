import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  advance,
  clearClip,
  dbToX,
  initialMeter,
  isClipping,
  METER_MAX_DB,
  METER_MIN_DB,
  meterVisible,
  TICKS_DB,
  zoneOf,
  zoneSegments,
} from "../level-meter.js";

describe("dbToX", () => {
  test("the scale runs from the floor to full scale, linear in dB", () => {
    assert.equal(dbToX(METER_MIN_DB, 140), 0);
    assert.equal(dbToX(METER_MAX_DB, 140), 140);
    assert.equal(dbToX((METER_MIN_DB + METER_MAX_DB) / 2, 140), 70);
  });
  test("below the floor and above full scale are clamped, a floor frame is empty", () => {
    assert.equal(dbToX(-90, 140), 0);
    assert.equal(dbToX(+6, 140), 140);
    assert.equal(dbToX(Number.NaN, 140), 0);
  });
  test("the two tick marks sit where the owner asked for them", () => {
    assert.deepEqual(TICKS_DB, [-18, -6]);
    assert.ok(dbToX(-18, 140) < dbToX(-6, 140));
  });
});

describe("zoneOf", () => {
  test("green up to -6, amber to -1, red above (inclusive upward)", () => {
    assert.equal(zoneOf(-30), "ok");
    assert.equal(zoneOf(-6.1), "ok");
    assert.equal(zoneOf(-6), "warn");
    assert.equal(zoneOf(-1.1), "warn");
    assert.equal(zoneOf(-1), "hot");
    assert.equal(zoneOf(0), "hot");
  });
});

describe("zoneSegments", () => {
  test("a level inside the green is one segment of its width", () => {
    assert.deepEqual(zoneSegments(-30, 100), [{ zone: "ok", from: 0, to: dbToX(-30, 100) }]);
  });
  test("a level in the red is three segments that meet", () => {
    const segs = zoneSegments(-0.5, 100);
    assert.deepEqual(
      segs.map((s) => s.zone),
      ["ok", "warn", "hot"],
    );
    assert.equal(segs[0].to, segs[1].from);
    assert.equal(segs[1].to, segs[2].from);
    assert.equal(segs[2].to, dbToX(-0.5, 100));
  });
  test("silence draws nothing", () => {
    assert.deepEqual(zoneSegments(-90, 100), []);
  });
});

describe("isClipping", () => {
  test("a peak at or above full scale on either channel", () => {
    assert.equal(isClipping({ l: 0, r: -20 }), true);
    assert.equal(isClipping({ l: -20, r: 1.2 }), true);
    assert.equal(isClipping({ l: -0.2, r: -0.1 }), false);
    assert.equal(isClipping({ l: -90, r: -90 }), false);
  });
});

const frame = (l, r, hold_l = l, hold_r = r) => ({ l, r, hold_l, hold_r });

describe("advance (the display's fall-off and the clip latch)", () => {
  test("a louder level shows at once", () => {
    const s = advance(initialMeter(), frame(-12, -20), 0.066);
    assert.equal(s.l, -12);
    assert.equal(s.r, -20);
  });
  test("a quieter level falls at the release speed, not at once", () => {
    let s = advance(initialMeter(), frame(-6, -6), 0.066);
    s = advance(s, frame(-60, -60), 0.5);
    assert.ok(s.l < -6 && s.l > -60);
    assert.equal(s.l, -6 - 0.5 * 24); // 24 dB a second
  });
  test("it never falls below the level that is playing", () => {
    let s = advance(initialMeter(), frame(-6, -6), 0.066);
    s = advance(s, frame(-30, -30), 100);
    assert.equal(s.l, -30);
  });
  test("the hold tick is what the server sent", () => {
    const s = advance(initialMeter(), frame(-12, -14, -6, -9), 0.066);
    assert.equal(s.holdL, -6);
    assert.equal(s.holdR, -9);
  });
  test("a clip latches and stays after the level drops, until it is cleared", () => {
    let s = advance(initialMeter(), frame(0.4, -10), 0.066);
    assert.equal(s.clip, true);
    s = advance(s, frame(-40, -40), 0.066);
    assert.equal(s.clip, true);
    s = clearClip(s);
    assert.equal(s.clip, false);
    s = advance(s, frame(-40, -40), 0.066);
    assert.equal(s.clip, false);
  });
  test("a floor frame (playback stopped) empties the bars and keeps a latched clip", () => {
    let s = advance(initialMeter(), frame(0, 0, 0, 0), 0.066);
    s = advance(s, frame(-90, -90, -90, -90), 0.066);
    assert.equal(s.l, METER_MIN_DB);
    assert.equal(s.holdL, METER_MIN_DB);
    assert.equal(s.clip, true);
  });
});

describe("meterVisible", () => {
  test("the bars show only while playing; a latched clip shows alone", () => {
    assert.deepEqual(meterVisible({ playing: true }, { clip: false }), {
      bars: true,
      clip: false,
    });
    assert.deepEqual(meterVisible({ playing: false }, { clip: false }), {
      bars: false,
      clip: false,
    });
    assert.deepEqual(meterVisible({ playing: false }, { clip: true }), {
      bars: false,
      clip: true,
    });
  });
});
