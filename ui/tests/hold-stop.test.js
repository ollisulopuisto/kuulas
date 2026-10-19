import assert from "node:assert/strict";
import test from "node:test";
import { createHoldStop } from "../hold-stop.js";

test("createHoldStop: hold 1999 ms then release does not stop", () => {
  const hs = createHoldStop();
  hs.press(1000);

  const t1 = hs.tick(1500);
  assert.equal(t1.holding, true);
  assert.equal(t1.progress, 0.25);
  assert.equal(t1.stopped, false);

  const t2 = hs.tick(2999);
  assert.equal(t2.holding, true);
  assert.equal(t2.progress, 1999 / 2000);
  assert.equal(t2.stopped, false);

  const r = hs.release(3000);
  assert.equal(r.stopped, false);

  const t3 = hs.tick(3100);
  assert.equal(t3.holding, false);
  assert.equal(t3.progress, 0);
  assert.equal(t3.stopped, false);
});

test("createHoldStop: hold 2000 ms stops once, next tick not stopped again", () => {
  const hs = createHoldStop();
  hs.press(1000);

  // At 1000 ms progress is 0.5
  const tHalf = hs.tick(2000);
  assert.equal(tHalf.holding, true);
  assert.equal(tHalf.progress, 0.5);
  assert.equal(tHalf.stopped, false);

  // At 2000 ms elapsed, stopped fires
  const tStop = hs.tick(3000);
  assert.equal(tStop.stopped, true);
  assert.equal(tStop.progress, 1);

  // Next tick after stopped fired: further tick returns stopped: false
  const tAfter = hs.tick(3100);
  assert.deepEqual(tAfter, { holding: false, progress: 0, stopped: false });

  // Further press and release also return inactive state until reset()
  assert.deepEqual(hs.press(3200), { holding: false, progress: 0, stopped: false });
  assert.deepEqual(hs.release(3300), { holding: false, progress: 0, stopped: false });
});

test("createHoldStop: custom holdMs", () => {
  const hs = createHoldStop({ holdMs: 500 });
  hs.press(0);

  const t1 = hs.tick(250);
  assert.equal(t1.holding, true);
  assert.equal(t1.progress, 0.5);
  assert.equal(t1.stopped, false);

  const t2 = hs.tick(500);
  assert.equal(t2.stopped, true);
  assert.equal(t2.progress, 1);
});

test("createHoldStop: second press while holding is ignored (keeps first start)", () => {
  const hs = createHoldStop();
  hs.press(1000);
  hs.press(2000); // ignored

  // At 3000 ms: elapsed since 1000 is 2000 ms -> stops
  const t = hs.tick(3000);
  assert.equal(t.stopped, true);
  assert.equal(t.progress, 1);
});

test("createHoldStop: time going backwards counts as 0 progress", () => {
  const hs = createHoldStop();
  hs.press(1000);

  const t = hs.tick(500);
  assert.equal(t.holding, true);
  assert.equal(t.progress, 0);
  assert.equal(t.stopped, false);
});

test("createHoldStop: tick or release without press is harmless", () => {
  const hs = createHoldStop();

  const t = hs.tick(1000);
  assert.deepEqual(t, { holding: false, progress: 0, stopped: false });

  const r = hs.release(1100);
  assert.equal(r.stopped, false);
});

test("createHoldStop: reset makes it reusable for the next take", () => {
  const hs = createHoldStop({ holdMs: 1000 });
  hs.press(0);
  assert.equal(hs.tick(1000).stopped, true);

  // Now locked in stopped state
  assert.equal(hs.tick(1100).stopped, false);
  assert.equal(hs.press(1200).holding, false);

  // Reset
  hs.reset();

  // Reusable for next take
  hs.press(2000);
  const t = hs.tick(2500);
  assert.equal(t.holding, true);
  assert.equal(t.progress, 0.5);
  assert.equal(t.stopped, false);

  assert.equal(hs.tick(3000).stopped, true);
});
