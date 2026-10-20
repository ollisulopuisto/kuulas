import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { backingSize, MAX_CANVAS_PIXELS } from "../canvas-size.js";
import { createTileStore } from "../tiles.js";

describe("canvas backing size", () => {
  test("a normal window keeps the full device ratio", () => {
    assert.deepEqual(backingSize(1440, 800, 2), { width: 2880, height: 1600, ratio: 2 });
  });

  test("a 5K full-screen timeline at ratio 2 is capped", () => {
    // A 5K display is 2560 x 1440 CSS pixels at ratio 2: 14.7 Mpx uncapped.
    const b = backingSize(2560, 1440, 2);
    assert.ok(b.width * b.height <= MAX_CANVAS_PIXELS);
    assert.ok(b.ratio < 2 && b.ratio > 1);
    // The aspect is kept.
    assert.ok(Math.abs(b.width / b.height - 2560 / 1440) < 0.01);
  });

  test("the cap holds even for a window larger than the cap at ratio 1", () => {
    const b = backingSize(10_000, 10_000, 1);
    assert.ok(b.width * b.height <= MAX_CANVAS_PIXELS);
  });

  test("a bad ratio counts as 1, a zero size is empty", () => {
    assert.deepEqual(backingSize(100, 50, Number.NaN), { width: 100, height: 50, ratio: 1 });
    assert.deepEqual(backingSize(0, 0, 2), { width: 0, height: 0, ratio: 2 });
  });

  test("the size never depends on the project's length or the zoom", () => {
    // Only the viewport's CSS size goes in: the timeline's canvases are the
    // stack's size (timeline.js measure), never the whole timeline's width.
    const source = readFileSync(new URL("../timeline.js", import.meta.url), "utf8");
    assert.match(source, /backingSize\(rect\.width, rect\.height/);
    for (const file of ["../waveform.worker.js", "../waveform-layer.js", "../overview.js"]) {
      const text = readFileSync(new URL(file, import.meta.url), "utf8");
      assert.match(text, /backingSize\(/, file);
      assert.doesNotMatch(text, /\.width = Math\.round\(/, file);
    }
  });
});

describe("the peak tile cache is capped", () => {
  test("no more than maxTiles tiles are kept however many arrive", async () => {
    const store = createTileStore({
      fetchTile: async () => new Float32Array(2048),
      onChange: () => {},
      maxTiles: 10,
      maxInflight: 100,
    });
    store.want(Array.from({ length: 50 }, (_, i) => ({ media: "m", level: 0, tile: i })));
    await new Promise((resolve) => setTimeout(resolve, 0));
    let held = 0;
    for (let i = 0; i < 50; i += 1) if (store.lookup("m", 0, i)) held += 1;
    assert.ok(held <= 10, `held ${held}`);
  });
});
