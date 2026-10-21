// Owner, 2026-10-21: "stutter in playback cursor's location again! jumps a few pixels
// back and then keeps continuing". A steady playback with anchors that are a little off
// (the device latency jitters, a callback is late, a poll answers with an older reading,
// an anchor arrives out of order) must draw a cursor that never steps back and never
// freezes; only a real discontinuity (new seq, seek, a jump of 150 ms or more) is taken
// at once.
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createPlayheadClock, JUMP_S, SLEW_MS } from "../playhead-clock.js";

const RATE = 48_000;
const MS = RATE / 1000; // frames per page millisecond at speed 1
const base = { rate: RATE, speed: 1, playing: true, seq: 1, skip: [], loop: null, end: null };
const msg = (position, tMs, extra = {}) => ({
  ...base,
  position,
  t: tMs / 1000,
  now: tMs / 1000,
  ...extra,
});

/** Deterministic pseudo-random numbers in [-1, 1). */
function noise(seed) {
  let s = seed;
  return () => {
    s = (s * 1_664_525 + 1_013_904_223) % 4_294_967_296;
    return (s / 4_294_967_296) * 2 - 1;
  };
}

/**
 * A steady playback of `seconds`: the truth is frame = (ms - 1000) * MS. Every 200 ms the
 * server sends a reading whose position is off by `err(i)` ms and which arrives `late(i)`
 * ms after it was heard. Frames are drawn every 16 ms. Returns the drawn frames.
 */
function run({ seconds = 10, err, late, order = (list) => list }) {
  const c = createPlayheadClock();
  c.setOffset(0);
  const truth = (ms) => (ms - 1000) * MS;
  const readings = [];
  for (let i = 0; i * 200 < seconds * 1000; i++) {
    const heardAt = 1000 + i * 200;
    readings.push({
      i,
      heardAt,
      arrives: heardAt + late(i),
      position: Math.round(truth(heardAt) + err(i) * MS),
    });
  }
  const queue = order(readings);
  const drawn = [];
  let next = 0;
  for (let now = 1000; now < 1000 + seconds * 1000; now += 16) {
    while (next < queue.length && queue[next].arrives <= now) {
      const r = queue[next++];
      c.accept(msg(r.position, r.heardAt), r.arrives);
    }
    if (next > 0) drawn.push({ now, frame: c.frameAt(now), truth: truth(now) });
  }
  return drawn;
}

function stepsOf(drawn) {
  return drawn.slice(1).map((d, i) => d.frame - drawn[i].frame);
}

const nominalStep = 16 * MS;

describe("a steady playback with imperfect anchors", () => {
  it("never steps back with +-30 ms of jitter, late and older readings", () => {
    const r = noise(7);
    const drawn = run({
      err: () => r() * 30,
      late: (i) => (i % 5 === 3 ? 90 : 5),
    });
    for (const step of stepsOf(drawn)) assert.ok(step >= 0, `stepped back by ${-step} frames`);
  });

  it("never steps back when a late callback makes a reading 80 ms behind", () => {
    const drawn = run({
      err: (i) => (i % 7 === 4 ? -80 : 0),
      late: () => 3,
    });
    for (const step of stepsOf(drawn)) assert.ok(step >= 0, `stepped back by ${-step} frames`);
  });

  it("does not freeze either: every step keeps at least a third of the nominal speed", () => {
    const r = noise(11);
    const drawn = run({ err: () => r() * 30, late: () => 5 });
    for (const step of stepsOf(drawn)) {
      assert.ok(step >= nominalStep / 3, `a step of ${step} frames is a stutter`);
    }
  });

  it("stays within 40 ms of the truth", () => {
    const r = noise(3);
    const drawn = run({ err: () => r() * 30, late: (i) => (i % 5 === 3 ? 90 : 5) });
    for (const { frame, truth } of drawn) {
      assert.ok(Math.abs(frame - truth) <= 40 * MS, `${(frame - truth) / MS} ms off`);
    }
  });

  it("ignores a reading that arrives out of order (older than the one already used)", () => {
    const drawn = run({
      err: () => 0,
      late: () => 5,
      order: (list) => {
        const out = [...list];
        [out[10], out[11]] = [out[11], out[10]]; // 11 arrives before 10, but 10 is older
        return out;
      },
    });
    for (const step of stepsOf(drawn)) assert.ok(step >= 0);
  });
});

describe("a correction behind the cursor is slewed, not jumped", () => {
  const clock = () => {
    const c = createPlayheadClock();
    c.setOffset(0);
    return c;
  };

  it("slows down for about SLEW_MS and then runs with the truth again", () => {
    const c = clock();
    c.accept(msg(0, 1000), 1000);
    const before = c.frameAt(1200); // 9600
    c.accept(msg(9600 - 60 * MS, 1200), 1200); // the reading is 60 ms behind
    const just = c.frameAt(1201);
    assert.ok(just >= before, "never back");
    assert.ok(just - before < MS, "slower than the sound for a moment");
    const end = c.frameAt(1200 + SLEW_MS);
    assert.equal(end, Math.round(9600 - 60 * MS + SLEW_MS * MS)); // on the new line
  });

  it("takes a jump of JUMP_S or more at once, either way", () => {
    const c = clock();
    c.accept(msg(0, 1000), 1000);
    c.frameAt(1200);
    c.accept(msg(9600 - JUMP_S * RATE - 100, 1200), 1200);
    assert.equal(c.frameAt(1200), 9600 - JUMP_S * RATE - 100);
    c.accept(msg(9600 + JUMP_S * RATE + 100 + 4800, 1300), 1300);
    assert.equal(c.frameAt(1300), 9600 + JUMP_S * RATE + 100 + 4800);
  });

  it("takes a new seq at once even when it is slightly behind", () => {
    const c = clock();
    c.accept(msg(0, 1000), 1000);
    c.frameAt(1200);
    c.accept(msg(9600 - 30 * MS, 1200, { seq: 2 }), 1200);
    assert.equal(c.frameAt(1200), Math.round(9600 - 30 * MS));
  });

  it("slews a reverse playback the same way (never forward)", () => {
    const c = clock();
    c.accept(msg(100_000, 1000, { speed: -1 }), 1000);
    const before = c.frameAt(1200);
    c.accept(msg(100_000 - 9600 + 40 * MS, 1200, { speed: -1 }), 1200); // 40 ms behind
    let last = before;
    for (let now = 1201; now < 1500; now += 7) {
      const f = c.frameAt(now);
      assert.ok(f <= last, "reverse never steps forward");
      last = f;
    }
  });
});
