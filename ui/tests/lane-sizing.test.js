import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  autoFitKey,
  DRAG_THRESHOLD,
  dragLaneHeight,
  dragStarted,
  explicitFit,
  fitHeight,
  pruneLaneHeights,
  scrollThumb,
  shouldAutoFit,
  withLaneHeight,
} from "../lane-sizing.js";
import { layoutRows, MAX_LANE, MIN_LANE } from "../lanes.js";

const tracks = (n, extra = {}) =>
  Array.from({ length: n }, (_, i) => ({ id: `t${i + 1}`, clips: [], ...extra }));
const project = (n) => ({ rate: 48_000, buses: [], tracks: tracks(n) });
const base = { busHeight: 32, groupGap: 14, laneHeights: {} };

describe("fitHeight", () => {
  test("splits the lane area evenly among the tracks", () => {
    assert.equal(fitHeight({ ...base, project: project(4), available: 400 }), 100);
  });

  test("rounds down so the lanes never overflow", () => {
    assert.equal(fitHeight({ ...base, project: project(3), available: 400 }), 133);
  });

  test("is clamped to the lane limits", () => {
    assert.equal(fitHeight({ ...base, project: project(1), available: 900 }), MAX_LANE);
    assert.equal(fitHeight({ ...base, project: project(40), available: 300 }), MIN_LANE);
  });

  test("bus rows and group gaps are taken off first", () => {
    const grouped = {
      rate: 48_000,
      buses: [{ id: "b1", name: "Voices" }],
      tracks: [
        { id: "t1", bus: "b1", clips: [] },
        { id: "t2", bus: "b1", clips: [] },
        { id: "t3", clips: [] },
      ],
    };
    // 32 bus row + 14 gap = 46 fixed; 3 lanes share 400 - 46.
    assert.equal(fitHeight({ ...base, project: grouped, available: 400 }), 118);
  });

  test("a one-track bus is merged: no row of its own", () => {
    const merged = {
      rate: 48_000,
      buses: [{ id: "b1", name: "Voices" }],
      tracks: [{ id: "t1", bus: "b1", clips: [] }],
    };
    assert.equal(fitHeight({ ...base, project: merged, available: 100 }), 100);
  });

  test("a lane with its own height keeps it; the rest share what is left", () => {
    const laneHeights = { t1: 60 };
    assert.equal(fitHeight({ ...base, project: project(4), available: 400, laneHeights }), 113);
  });

  test("nothing to fit: no tracks, every lane sized by hand, or no room measured", () => {
    assert.equal(fitHeight({ ...base, project: project(0), available: 400 }), null);
    assert.equal(
      fitHeight({ ...base, project: project(1), available: 400, laneHeights: { t1: 50 } }),
      null,
    );
    assert.equal(fitHeight({ ...base, project: project(2), available: 0 }), null);
    assert.equal(fitHeight({ ...base, project: null, available: 400 }), null);
  });

  test("the fitted layout fits the lane area", () => {
    const p = project(7);
    const height = fitHeight({ ...base, project: p, available: 650 });
    const layout = layoutRows(p, height, base);
    assert.ok(layout.height <= 650);
    assert.ok(layout.height > 650 - 7);
  });
});

describe("dragLaneHeight", () => {
  test("follows the pointer from where the drag began", () => {
    assert.equal(dragLaneHeight({ startHeight: 80, startY: 200, y: 230 }), 110);
    assert.equal(dragLaneHeight({ startHeight: 80, startY: 200, y: 190 }), 70);
  });
  test("respects min and max", () => {
    assert.equal(dragLaneHeight({ startHeight: 80, startY: 200, y: -500 }), MIN_LANE);
    assert.equal(dragLaneHeight({ startHeight: 80, startY: 200, y: 900 }), MAX_LANE);
  });
  test("a junk pointer position leaves the height as it was", () => {
    assert.equal(dragLaneHeight({ startHeight: 80, startY: 200, y: Number.NaN }), 80);
  });
});

describe("withLaneHeight and pruneLaneHeights", () => {
  test("sets, replaces and (null) resets one lane without touching the old map", () => {
    const before = { t1: 50 };
    const set = withLaneHeight(before, "t2", 90);
    assert.deepEqual(set, { t1: 50, t2: 90 });
    assert.deepEqual(before, { t1: 50 });
    assert.deepEqual(withLaneHeight(set, "t1", null), { t2: 90 });
  });
  test("a height is clamped on the way in", () => {
    assert.deepEqual(withLaneHeight({}, "t1", 5000), { t1: MAX_LANE });
  });
  test("prune drops tracks that are gone", () => {
    assert.deepEqual(pruneLaneHeights({ t1: 50, gone: 70 }, project(2)), { t1: 50 });
  });
});

describe("auto-fit trigger", () => {
  const input = { ...base, project: project(3), available: 400 };
  test("the key changes with the lane area, the tracks, the buses and the sizes", () => {
    const key = autoFitKey(input);
    assert.notEqual(autoFitKey({ ...input, available: 401 }), key);
    assert.notEqual(autoFitKey({ ...input, project: project(4) }), key);
    assert.notEqual(
      autoFitKey({
        ...input,
        project: { ...project(3), tracks: tracks(3).map((t) => ({ ...t, bus: "b" })) },
      }),
      key,
    );
    assert.notEqual(autoFitKey({ ...input, laneHeights: { t1: 50 } }), key);
    assert.notEqual(autoFitKey({ ...input, busHeight: 24 }), key);
  });
  test("the key ignores things that do not move the lanes (clips, names, gain)", () => {
    const key = autoFitKey(input);
    const edited = {
      ...project(3),
      tracks: tracks(3, { gain_db: 3, name: "x", clips: [{ id: "c" }] }),
    };
    assert.equal(autoFitKey({ ...input, project: edited }), key);
  });
  test("fits when on and something changed; not when off, unchanged or unmeasured", () => {
    const key = autoFitKey(input);
    assert.equal(shouldAutoFit({ on: true, key, last: "" }), true);
    assert.equal(shouldAutoFit({ on: true, key, last: key }), false);
    assert.equal(shouldAutoFit({ on: false, key, last: "" }), false);
    const unmeasured = autoFitKey({ ...input, available: 0 });
    assert.equal(shouldAutoFit({ on: true, key: unmeasured, last: "" }), false);
    const noProject = autoFitKey({ ...input, project: null });
    assert.equal(shouldAutoFit({ on: true, key: noProject, last: "" }), false);
  });
});

describe("a border drag needs a real drag", () => {
  test("a click or a move under 4 px never starts it", () => {
    assert.equal(DRAG_THRESHOLD, 4);
    assert.equal(dragStarted({ startY: 200, y: 200 }), false);
    assert.equal(dragStarted({ startY: 200, y: 203 }), false);
    assert.equal(dragStarted({ startY: 200, y: 197 }), false);
  });
  test("4 px either way does, and junk does not", () => {
    assert.equal(dragStarted({ startY: 200, y: 204 }), true);
    assert.equal(dragStarted({ startY: 200, y: 196 }), true);
    assert.equal(dragStarted({ startY: 200, y: Number.NaN }), false);
  });
});

describe("explicitFit (View > Fit tracks to window)", () => {
  test("hand-sized lanes are cleared and every track is fitted", () => {
    const input = { ...base, project: project(4), available: 400, laneHeights: { t1: 40 } };
    assert.equal(fitHeight(input), 120); // auto-fit keeps t1 at 40: the others share 360
    assert.deepEqual(explicitFit(input), { laneHeight: 100, laneHeights: {} });
  });
  test("with every lane hand-sized it still fits (fitHeight alone gives null)", () => {
    const input = {
      ...base,
      project: project(2),
      available: 200,
      laneHeights: { t1: 40, t2: 50 },
    };
    assert.equal(fitHeight(input), null);
    assert.deepEqual(explicitFit(input), { laneHeight: 100, laneHeights: {} });
  });
  test("nothing to fit gives null", () => {
    assert.equal(explicitFit({ ...base, project: null, available: 400 }), null);
  });
});

describe("scrollThumb (the lanes area scroll indicator)", () => {
  test("none while everything fits", () => {
    assert.equal(scrollThumb({ contentHeight: 300, viewHeight: 300, scrollY: 0 }), null);
    assert.equal(scrollThumb({ contentHeight: 100, viewHeight: 300, scrollY: 0 }), null);
  });
  test("size is the visible share, position follows the scroll", () => {
    assert.deepEqual(scrollThumb({ contentHeight: 600, viewHeight: 300, scrollY: 0 }), {
      top: 0,
      height: 150,
    });
    assert.deepEqual(scrollThumb({ contentHeight: 600, viewHeight: 300, scrollY: 300 }), {
      top: 150,
      height: 150,
    });
  });
  test("never thinner than 24 px, never past the end", () => {
    const thumb = scrollThumb({ contentHeight: 30_000, viewHeight: 300, scrollY: 99_999 });
    assert.equal(thumb.height, 24);
    assert.equal(thumb.top, 276);
  });
});
