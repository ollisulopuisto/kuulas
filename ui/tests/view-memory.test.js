import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { changeKey, createSaver, recordOf, restoreFrom } from "../view-memory.js";

const project = { rate: 48000, tracks: [{ id: "t1" }, { id: "t2" }] };
const context = { project, width: 1000, totalFrames: 480_000 };
const state = {
  zoom: 12,
  scroll: 4800,
  laneHeight: 96,
  laneHeights: { t1: 50 },
  autoFitTracks: true,
  waveformMode: "full",
  followMode: "continuous",
  focusTrack: "t2",
  sidebarTab: "history",
  playhead: 24_000,
  playing: false,
  inPoint: 1000,
  outPoint: 5000,
};

describe("recordOf", () => {
  test("keeps the view fields and nothing else", () => {
    const record = recordOf({ ...state, project, selection: new Set(["c1"]) }, { whole: false });
    assert.deepEqual(record, {
      zoom: 12,
      scroll: 4800,
      whole: false,
      laneHeight: 96,
      laneHeights: { t1: 50 },
      autoFitTracks: true,
      waveformMode: "full",
      followMode: "continuous",
      focusTrack: "t2",
      sidebarTab: "history",
      playhead: 24_000,
      inPoint: 1000,
      outPoint: 5000,
      loop: false,
    });
  });
  test("remembers the loop switch", () => {
    assert.equal(recordOf({ ...state, loop: true }).loop, true);
  });
});

describe("restoreFrom", () => {
  test("brings the loop switch back, only if it is a boolean", () => {
    assert.equal(restoreFrom({ loop: true }, context).patch.loop, true);
    assert.equal(restoreFrom({ loop: false }, context).patch.loop, false);
    assert.equal("loop" in restoreFrom({ loop: "yes" }, context).patch, false);
    assert.equal("loop" in restoreFrom({}, context).patch, false);
  });

  test("round-trips a record", () => {
    const back = restoreFrom(recordOf(state, { whole: false }), context);
    assert.equal(back.whole, false);
    assert.deepEqual(back.patch, {
      zoom: 12,
      scroll: 4800,
      laneHeight: 96,
      laneHeights: { t1: 50 },
      autoFitTracks: true,
      waveformMode: "full",
      followMode: "continuous",
      focusTrack: "t2",
      sidebarTab: "history",
      playhead: 24_000,
      inPoint: 1000,
      outPoint: 5000,
      loop: false,
    });
  });

  test("nothing remembered, or junk, restores nothing", () => {
    for (const junk of [null, undefined, 5, "x", [], {}]) {
      assert.deepEqual(restoreFrom(junk, context).patch, {});
    }
  });

  test("clamps zoom and scroll to the project", () => {
    const wide = restoreFrom({ zoom: 1e9, scroll: 1e12 }, context).patch;
    assert.equal(wide.zoom, 480_000 / 1000); // never wider than the whole edit
    assert.equal(wide.scroll, 0);
    const close = restoreFrom({ zoom: 0, scroll: -50 }, context).patch;
    assert.equal(close.zoom, 1 / 8);
    assert.equal(close.scroll, 0);
    const late = restoreFrom({ zoom: 10, scroll: 1e12 }, context).patch;
    assert.ok(late.scroll <= 480_000);
  });

  test("clamps the play cursor and the marks to the project length", () => {
    const patch = restoreFrom({ playhead: 9e9, inPoint: -5, outPoint: 9e9 }, context).patch;
    assert.equal(patch.playhead, 480_000);
    assert.equal(patch.inPoint, 0);
    assert.equal(patch.outPoint, 480_000);
  });

  test("marks that are not a range are dropped together", () => {
    const patch = restoreFrom({ inPoint: 9000, outPoint: 100 }, context).patch;
    assert.equal(patch.inPoint, null);
    assert.equal(patch.outPoint, null);
  });

  test("ignores unknown tabs, modes and tracks", () => {
    const patch = restoreFrom(
      { sidebarTab: "nope", waveformMode: "x", followMode: "y", focusTrack: "gone" },
      context,
    ).patch;
    assert.deepEqual(patch, {});
  });

  test("ignores numbers that are not numbers", () => {
    const patch = restoreFrom(
      { zoom: "12", scroll: Number.NaN, laneHeight: null, playhead: Infinity },
      context,
    ).patch;
    assert.deepEqual(patch, {});
  });

  test("clamps the lane height", () => {
    assert.equal(restoreFrom({ laneHeight: 9999 }, context).patch.laneHeight, 160);
  });

  test("per-lane heights: clamped, only for tracks that exist, numbers only", () => {
    const patch = restoreFrom(
      { laneHeights: { t1: 9999, t2: 3, gone: 70, bad: "x" } },
      context,
    ).patch;
    assert.deepEqual(patch.laneHeights, { t1: 160, t2: 24 });
    assert.equal(restoreFrom({ laneHeights: [1, 2] }, context).patch.laneHeights, undefined);
    assert.equal(restoreFrom({ laneHeights: "x" }, context).patch.laneHeights, undefined);
  });

  test("auto-fit is restored only as a real boolean", () => {
    assert.equal(restoreFrom({ autoFitTracks: true }, context).patch.autoFitTracks, true);
    assert.equal(restoreFrom({ autoFitTracks: false }, context).patch.autoFitTracks, false);
    assert.equal(restoreFrom({ autoFitTracks: "yes" }, context).patch.autoFitTracks, undefined);
  });

  test("a state without these fields records them as empty and off", () => {
    const record = recordOf({ ...state, laneHeights: undefined, autoFitTracks: undefined });
    assert.deepEqual(record.laneHeights, {});
    assert.equal(record.autoFitTracks, false);
  });

  test("keeps unknown keys out of the patch (they stay in the file)", () => {
    assert.deepEqual(restoreFrom({ future: 1 }, context).patch, {});
  });
});

describe("changeKey", () => {
  test("the play cursor does not change the key while playing", () => {
    const a = changeKey({ ...state, playing: true, playhead: 1 });
    const b = changeKey({ ...state, playing: true, playhead: 2 });
    assert.equal(a, b);
  });
  test("it does when stopped", () => {
    assert.notEqual(changeKey({ ...state, playhead: 1 }), changeKey({ ...state, playhead: 2 }));
  });
});

describe("createSaver", () => {
  function setup() {
    const saved = [];
    const timers = new Map();
    let next = 1;
    const saver = createSaver({
      save: (record) => saved.push(record),
      delay: 800,
      setTimer: (fn, ms) => {
        timers.set(next, { fn, ms });
        return next++;
      },
      clearTimer: (id) => timers.delete(id),
    });
    const fire = () => {
      for (const [id, timer] of [...timers]) {
        timers.delete(id);
        timer.fn();
      }
    };
    return { saver, saved, timers, fire };
  }

  test("saves once after a burst of changes, with the latest record", () => {
    const { saver, saved, timers, fire } = setup();
    for (let n = 0; n < 50; n += 1) saver.touch(() => ({ zoom: n }));
    assert.equal(timers.size, 1);
    assert.equal(saved.length, 0);
    fire();
    assert.deepEqual(saved, [{ zoom: 49 }]);
  });

  test("flush saves at once and cancels the timer", () => {
    const { saver, saved, timers } = setup();
    saver.touch(() => ({ zoom: 1 }));
    saver.flush();
    assert.deepEqual(saved, [{ zoom: 1 }]);
    assert.equal(timers.size, 0);
    saver.flush();
    assert.equal(saved.length, 1, "nothing pending, nothing sent");
  });

  test("an unchanged record is not sent again", () => {
    const { saver, saved, fire } = setup();
    saver.touch(() => ({ zoom: 1 }));
    fire();
    saver.touch(() => ({ zoom: 1 }));
    fire();
    assert.equal(saved.length, 1);
  });

  test("a failing save is swallowed and tried again later", () => {
    let fail = true;
    const saved = [];
    const saver = createSaver({
      save: (record) => {
        if (fail) throw new Error("offline");
        saved.push(record);
      },
      setTimer: () => 1,
      clearTimer: () => {},
    });
    saver.touch(() => ({ zoom: 1 }));
    saver.flush();
    fail = false;
    saver.touch(() => ({ zoom: 1 }));
    saver.flush();
    assert.deepEqual(saved, [{ zoom: 1 }]);
  });

  test("a rejected promise from save is swallowed too", async () => {
    const saver = createSaver({
      save: () => Promise.reject(new Error("offline")),
      setTimer: () => 1,
      clearTimer: () => {},
    });
    saver.touch(() => ({ zoom: 1 }));
    saver.flush();
    await new Promise((resolve) => setImmediate(resolve));
  });
});
