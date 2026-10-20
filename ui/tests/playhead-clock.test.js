import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  anchorFrom,
  bestOffset,
  createPlayheadClock,
  MAX_AHEAD_MS,
  project,
  SNAP_S,
} from "../playhead-clock.js";

const RATE = 48_000;
const base = { rate: RATE, speed: 1, playing: true, seq: 1, skip: [], loop: null, end: null };

describe("bestOffset", () => {
  it("takes the sample with the shortest round trip, midpoint rule", () => {
    const offset = bestOffset([
      { sent: 100, received: 140, server: 10.05 }, // rtt 40
      { sent: 200, received: 204, server: 10.152 }, // rtt 4: best
    ]);
    assert.equal(offset, 10_152 - 202);
  });
  it("is null with no samples", () => assert.equal(bestOffset([]), null));
});

describe("anchorFrom", () => {
  it("maps the server time with the offset", () => {
    const a = anchorFrom(
      { ...base, position: 10, t: 5, now: 5.01 },
      { offset: 4000, receivedAt: 0 },
    );
    assert.equal(a.at, 1000);
  });
  it("without an offset dates it by the anchor's age on arrival", () => {
    const a = anchorFrom(
      { ...base, position: 10, t: 5, now: 5.02 },
      { offset: null, receivedAt: 900 },
    );
    assert.ok(Math.abs(a.at - 880) < 1e-9);
  });
});

describe("project", () => {
  const a = { ...base, frame: 1000, at: 0 };
  it("moves at speed x rate", () => {
    assert.equal(project(a, 100), 1000 + 4800);
    assert.equal(project({ ...a, speed: 1.5 }, 100), 1000 + 7200);
    assert.equal(project({ ...a, speed: -2, frame: 100_000 }, 100), 100_000 - 9600);
  });
  it("holds before the anchor's time (audio not heard yet)", () => {
    assert.equal(project({ ...a, at: 50 }, 20), 1000);
  });
  it("stands still when stopped", () => assert.equal(project({ ...a, playing: false }, 500), 1000));
  it("jumps over skipped ranges forward and backward", () => {
    assert.equal(project({ ...a, skip: [[2000, 3000]] }, 100), 1000 + 4800 + 1000);
    const back = { ...a, frame: 10_000, speed: -1, skip: [[5000, 8000]] };
    assert.equal(project(back, 100), 10_000 - 4800 - 3000);
  });
  it("wraps in a loop", () => {
    assert.equal(project({ ...a, loop: [0, 4000] }, 100), (1000 + 4800) % 4000);
  });
  it("stops at the run's end", () => {
    assert.equal(project({ ...a, end: 3000 }, 100), 3000);
    assert.equal(project({ ...a, frame: 2000, speed: -1, end: 0 }, 100), 0);
  });
  it("does not run on for ever without news", () => {
    assert.equal(project(a, 60_000), 1000 + (MAX_AHEAD_MS / 1000) * RATE);
  });
});

describe("createPlayheadClock", () => {
  const msg = (position, t, extra = {}) => ({ ...base, position, t, now: t, ...extra });
  const clock = () => {
    const c = createPlayheadClock();
    c.setOffset(0); // server seconds * 1000 = page ms
    return c;
  };

  it("extrapolates between corrections", () => {
    const c = clock();
    c.accept(msg(0, 1), 1000);
    assert.equal(c.frameAt(1100), 4800);
  });

  it("absorbs a small backward correction instead of jittering back", () => {
    const c = clock();
    c.accept(msg(0, 1), 1000);
    assert.equal(c.frameAt(1200), 9600);
    c.accept(msg(9600 - 480, 1.2), 1200); // 10 ms behind what was shown
    assert.equal(c.frameAt(1201), 9600); // held
    assert.ok(c.frameAt(1250) > 9600); // and moves on once caught up
  });

  it("snaps when a correction is far off", () => {
    const c = clock();
    c.accept(msg(0, 1), 1000);
    c.frameAt(1200);
    const behind = 9600 - Math.round(SNAP_S * RATE) - 4800;
    c.accept(msg(behind, 1.2), 1200);
    assert.equal(c.frameAt(1200), behind);
  });

  it("follows a new sequence at once (a seek, a loop wrap restart)", () => {
    const c = clock();
    c.accept(msg(50_000, 1), 1000);
    c.frameAt(1100);
    c.accept(msg(100, 1.1, { seq: 2 }), 1100);
    assert.equal(c.frameAt(1100), 100);
  });

  it("drops an anchor older than the newest seen", () => {
    const c = clock();
    c.accept(msg(100, 1, { seq: 5 }), 1000);
    assert.equal(c.accept(msg(9, 1, { seq: 4 }), 1000), false);
    assert.equal(c.frameAt(1000), 100);
  });

  it("a speed change carries on from where it is", () => {
    const c = clock();
    c.accept(msg(0, 1), 1000);
    c.accept(msg(4800, 1.1, { seq: 2, speed: 2 }), 1100);
    assert.equal(c.frameAt(1200), 4800 + 9600);
  });

  it("reverse never jitters forward", () => {
    const c = clock();
    c.accept(msg(100_000, 1, { speed: -1 }), 1000);
    assert.equal(c.frameAt(1100), 100_000 - 4800);
    c.accept(msg(100_000 - 4800 + 240, 1.1, { speed: -1 }), 1100);
    assert.equal(c.frameAt(1100), 100_000 - 4800);
  });

  it("stop freezes at once, ignores late playing anchors, then settles on the heard frame", () => {
    const c = clock();
    c.accept(msg(0, 1, { seq: 3 }), 1000);
    const frozen = c.stop(1100);
    assert.equal(frozen, 4800);
    assert.equal(c.frameAt(1500), 4800);
    assert.equal(c.accept(msg(9600, 1.2, { seq: 3 }), 1200), false); // sent before the stop
    assert.equal(c.frameAt(1500), 4800);
    c.settle(4700); // the engine's heard frame (the stop's answer)
    assert.equal(c.frameAt(1600), 4700);
    assert.equal(c.playing(), false);
    c.accept(msg(4700, 1.6, { seq: 4 }), 1600); // played again
    assert.equal(c.frameAt(1700), 4700 + 4800);
  });

  it("a stopped anchor ends a stop that is waiting", () => {
    const c = clock();
    c.accept(msg(0, 1, { seq: 3 }), 1000);
    c.stop(1100);
    assert.equal(c.accept(msg(4750, 1.1, { seq: 4, playing: false }), 1150), true);
    assert.equal(c.frameAt(1300), 4750);
  });

  it("a seek while playing moves the cursor at once and plays on from there", () => {
    const c = clock();
    c.accept(msg(0, 1, { seq: 3 }), 1000);
    c.jump(96_000, 1100);
    assert.equal(c.frameAt(1100), 96_000);
    assert.equal(c.frameAt(1200), 96_000 + 4800);
    c.accept(msg(96_000, 1.15, { seq: 4 }), 1210); // the engine's anchor for it
    assert.equal(c.frameAt(1250), 96_000 + 4800);
  });
});
