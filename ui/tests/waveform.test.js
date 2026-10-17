import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  clipTiles,
  columnsFromTiles,
  LEVELS,
  pickLevel,
  TILE_PEAKS,
  waveformColumns,
} from "../waveform.js";

const pairs = (...values) => Float32Array.from(values.flat());

describe("waveformColumns", () => {
  test("half waveform: a bar rising from the bottom edge by max(|min|, |max|)", () => {
    const out = waveformColumns(pairs([-0.5, 0.25], [-0.1, 1]), "half", "linear", 40);
    assert.deepEqual(Array.from(out), [20, 40, 0, 40]);
  });

  test("full waveform: min and max around the centre line", () => {
    const out = waveformColumns(pairs([-0.5, 1], [0, 0]), "full", "linear", 40);
    // centre 20: max 1 reaches the top (0), min -0.5 goes a quarter of the height below.
    assert.deepEqual(Array.from(out), [0, 30, 20, 20]);
  });

  test("the dB scale lifts quiet speech: -48 dBFS is the bottom, 0 dBFS the top", () => {
    const quiet = 10 ** (-24 / 20);
    const out = waveformColumns(
      pairs([-quiet, quiet], [0, 1], [0, 10 ** (-60 / 20)]),
      "half",
      "db",
      48,
    );
    assert.ok(Math.abs(out[0] - 24) < 1e-6, "-24 dBFS is half the height");
    assert.equal(out[2], 0, "0 dBFS fills the lane");
    assert.equal(out[4], out[5], "below the floor draws nothing");
  });

  test("any real signal draws at least a pixel, silence draws none", () => {
    const out = waveformColumns(pairs([-0.001, 0.001], [0, 0]), "half", "linear", 40);
    assert.equal(out[1] - out[0], 1);
    assert.equal(out[3] - out[2], 0);
  });

  test("a gain factor scales the drawing and clips at full height", () => {
    const out = waveformColumns(pairs([-0.4, 0.4]), "half", "linear", 40, 4);
    assert.equal(out[0], 0);
  });
});

describe("choosing tiles", () => {
  test("pickLevel takes the coarsest level that still has a peak per pixel", () => {
    assert.equal(pickLevel(1), LEVELS[0]);
    assert.equal(pickLevel(256), 256);
    assert.equal(pickLevel(1000), 256);
    assert.equal(pickLevel(1024), 1024);
    assert.equal(pickLevel(5000), 4096);
    assert.equal(pickLevel(1e9), 65536);
  });

  test("clipTiles lists the tiles that cover a source range", () => {
    const span = LEVELS[0] * TILE_PEAKS;
    assert.deepEqual(clipTiles(0, span - 1, 256), [0]);
    assert.deepEqual(clipTiles(span - 10, span + 10, 256), [0, 1]);
    assert.deepEqual(clipTiles(-500, 10, 256), [0], "before the start is clamped");
  });

  test("columnsFromTiles merges peaks per pixel and reports missing tiles", () => {
    const tile = new Float32Array(TILE_PEAKS * 2);
    for (let i = 0; i < TILE_PEAKS; i += 1) {
      tile[2 * i] = -(i % 10) / 10;
      tile[2 * i + 1] = (i % 10) / 10;
    }
    const lookup = (index) => (index === 0 ? tile : undefined);
    // 512 frames per pixel = 2 peaks per pixel at level 256.
    const { data, missing } = columnsFromTiles({
      lookup,
      level: 256,
      startFrame: 0,
      framesPerPixel: 512,
      count: 3,
    });
    assert.deepEqual(Array.from(data), [-0.1, 0.1, -0.3, 0.3, -0.5, 0.5].map(Math.fround));
    assert.deepEqual(missing, []);
    const gap = columnsFromTiles({
      lookup,
      level: 256,
      startFrame: 256 * TILE_PEAKS,
      framesPerPixel: 256,
      count: 2,
    });
    assert.deepEqual(gap.missing, [1]);
    assert.deepEqual(Array.from(gap.data), [0, 0, 0, 0]);
  });

  test("fewer than one peak per pixel repeats the nearest peak", () => {
    const tile = new Float32Array(TILE_PEAKS * 2);
    tile[0] = -0.5;
    tile[1] = 0.5;
    const { data } = columnsFromTiles({
      lookup: () => tile,
      level: 256,
      startFrame: 0,
      framesPerPixel: 64,
      count: 4,
    });
    assert.deepEqual(Array.from(data), [-0.5, 0.5, -0.5, 0.5, -0.5, 0.5, -0.5, 0.5]);
  });
});
