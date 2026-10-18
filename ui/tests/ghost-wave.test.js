import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { ghostColumns, ghostWindow, windowCovers } from "../ghost-wave.js";
import { TILE_PEAKS } from "../waveform.js";

// One tile at level 256 where peak p is [-p/1000, p/1000].
const tile = new Float32Array(TILE_PEAKS * 2);
for (let p = 0; p < TILE_PEAKS; p += 1) {
  tile[2 * p] = -p / 1000;
  tile[2 * p + 1] = p / 1000;
}
const lookup = (index) => (index === 0 ? tile : undefined);
const thousandths = (data) => [...data].map((v) => Math.round(v * 1000));

describe("ghostColumns", () => {
  test("one column per pixel of the clip's length, from its offset", () => {
    const { data } = ghostColumns({ lookup, offset: 256 * 10, length: 256 * 4, zoom: 256 });
    assert.deepEqual(thousandths(data), [-10, 10, -11, 11, -12, 12, -13, 13]);
  });

  test("clip gain scales the peaks like the lane", () => {
    const { data } = ghostColumns({
      lookup,
      offset: 256 * 100,
      length: 256,
      zoom: 256,
      gainDb: -6.0206,
    });
    assert.ok(Math.abs(data[1] - 0.05) < 1e-4);
  });

  test("a window selects columns without building the rest", () => {
    const { data, first } = ghostColumns({
      lookup,
      offset: 0,
      length: 256 * 100,
      zoom: 256,
      first: 50,
      count: 2,
    });
    assert.equal(first, 50);
    assert.deepEqual(thousandths(data), [-50, 50, -51, 51]);
  });

  test("never more columns than the clip has", () => {
    const { data } = ghostColumns({ lookup, offset: 0, length: 256 * 3, zoom: 256, count: 99 });
    assert.equal(data.length, 6);
  });

  test("tiles not loaded yet are reported and the columns stay silent", () => {
    const { data, missing } = ghostColumns({
      lookup: () => undefined,
      offset: 0,
      length: 256 * 2,
      zoom: 256,
    });
    assert.deepEqual(missing, [0]);
    assert.ok([...data].every((v) => v === 0));
  });

  test("a partial last pixel still gets a column", () => {
    const { data } = ghostColumns({ lookup, offset: 0, length: 256 * 2 + 1, zoom: 256 });
    assert.equal(data.length, 6);
  });
});

describe("ghostWindow", () => {
  test("a ghost fully on screen gives all its columns", () => {
    assert.deepEqual(ghostWindow(10, 50, 800), { first: 0, count: 50 });
  });
  test("a ghost cut by the left edge skips the hidden columns", () => {
    assert.deepEqual(ghostWindow(-30, 100, 800), { first: 30, count: 70 });
  });
  test("a ghost cut by the right edge stops at the screen", () => {
    assert.deepEqual(ghostWindow(780, 100, 800), { first: 0, count: 20 });
  });
  test("off screen gives null", () => {
    assert.equal(ghostWindow(-200, 100, 800), null);
    assert.equal(ghostWindow(800, 100, 800), null);
  });
  test("a very long ghost is bounded by the screen, with a margin", () => {
    assert.deepEqual(ghostWindow(-5000, 1_000_000, 800, 100), { first: 4900, count: 1000 });
  });
});

describe("windowCovers", () => {
  test("true when the built window contains the needed one", () => {
    assert.equal(windowCovers({ first: 0, count: 100 }, { first: 10, count: 50 }), true);
    assert.equal(windowCovers({ first: 20, count: 100 }, { first: 10, count: 50 }), false);
    assert.equal(windowCovers(null, { first: 0, count: 1 }), false);
  });
});
