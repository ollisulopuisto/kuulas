import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createLiveTake, dbToPeak } from "../live-take.js";

const S = 48000;

describe("dbToPeak", () => {
  test("0 dBFS is full scale, -20 is a tenth, silence is nothing", () => {
    assert.equal(dbToPeak(0), 1);
    assert.ok(Math.abs(dbToPeak(-20) - 0.1) < 1e-6);
    assert.equal(dbToPeak(-120), 0);
    assert.equal(dbToPeak(Number.NaN), 0);
    assert.equal(dbToPeak(6), 1);
  });
});

describe("createLiveTake: the take drawn on the lanes while it records", () => {
  const take = () => {
    const live = createLiveTake();
    live.begin({ at: 10 * S, preroll: 0, lanes: [{ trackId: "t1" }, { trackId: null }] });
    return live;
  };

  test("nothing before it begins", () => {
    const live = createLiveTake();
    assert.equal(live.active, false);
    assert.deepEqual(live.lanes(), []);
  });

  test("lanes name their track; a new track (no id yet) has no lane to draw on", () => {
    const live = take();
    assert.equal(live.active, true);
    assert.deepEqual(
      live.lanes().map((l) => l.trackId),
      ["t1"],
    );
  });

  test("a level event adds one peak per lane at the take's position on the timeline", () => {
    const live = take();
    live.push(S, [-6, -20]); // one second in
    const cols = live.columns(0, { scroll: 0, zoom: 480, width: 400 });
    // 10 s + 1 s = 11 s = frame 528000 -> pixel 1100: off the 400 px view
    assert.equal(cols.length, 400);
    assert.ok(cols.every((v) => v === 0));
    const wide = live.columns(0, { scroll: 10 * S, zoom: 480, width: 400 });
    // 1 s after the scroll = 48000 / 480 = pixel 100
    assert.ok(Math.abs(wide[100] - dbToPeak(-6)) < 1e-6);
  });

  test("a peak covers the stretch since the previous event, so the drawing has no holes", () => {
    const live = take();
    live.push(S, [-6, -6]);
    live.push(2 * S, [-12, -6]);
    const cols = live.columns(0, { scroll: 10 * S, zoom: 480, width: 400 });
    assert.ok(cols[150] > 0, "inside the second event's stretch");
    assert.ok(Math.abs(cols[150] - dbToPeak(-12)) < 1e-6);
    assert.ok(Math.abs(cols[50] - dbToPeak(-6)) < 1e-6, "inside the first event's stretch");
    assert.equal(cols[250], 0, "past the end of the take so far");
  });

  test("a pixel holding several peaks shows the loudest", () => {
    const live = take();
    for (let i = 1; i <= 10; i += 1) live.push(i * 100, [i === 5 ? -3 : -30, -30]);
    const cols = live.columns(0, { scroll: 10 * S, zoom: 48000, width: 4 });
    assert.ok(Math.abs(cols[0] - dbToPeak(-3)) < 1e-6);
  });

  test("pre-roll: the take's clock starts before Record was pressed", () => {
    const live = createLiveTake();
    live.begin({ at: 10 * S, preroll: 2 * S, lanes: [{ trackId: "t1" }] });
    live.push(3 * S, [-6]); // 3 s on the take's clock = 1 s after Record
    const cols = live.columns(0, { scroll: 10 * S, zoom: 480, width: 400 });
    assert.ok(cols[100] > 0);
    assert.equal(cols[250], 0);
  });

  test("the first events inside the pre-roll land before the take's start", () => {
    const live = createLiveTake();
    live.begin({ at: 10 * S, preroll: 2 * S, lanes: [{ trackId: "t1" }] });
    live.push(S, [-6]); // 1 s on the clock = 1 s BEFORE Record
    const cols = live.columns(0, { scroll: 9 * S, zoom: 480, width: 400 });
    assert.ok(cols[0] > 0 || cols[99] > 0 || cols[100] > 0);
  });

  test("reset forgets the take", () => {
    const live = take();
    live.push(S, [-6, -6]);
    live.reset();
    assert.equal(live.active, false);
    assert.deepEqual(live.lanes(), []);
  });

  test("a readings list shorter than the lanes counts the missing as silence", () => {
    const live = take();
    live.push(S, [-6]);
    const cols = live.columns(1, { scroll: 10 * S, zoom: 480, width: 400 });
    assert.ok(cols.every((v) => v === 0));
  });
});
