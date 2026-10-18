// WP57: the waveform follows the clip, envelope and track gain, and clipping after that gain is red.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { makeWaveformJob, paintWaveforms } from "../paint.js";
import { TILE_PEAKS } from "../waveform.js";

function fakeContext() {
  const calls = [];
  const sets = [];
  return {
    calls,
    sets,
    ctx: new Proxy(
      {},
      {
        get:
          (_t, name) =>
          (...args) =>
            calls.push([name, ...args]),
        set: (_t, name, value) => {
          sets.push([name, value]);
          return true;
        },
      },
    ),
  };
}

const palette = [{ fill: "#123", ink: "#fff", wave: "#456" }];
const RED = "#ff0000";
const job = (clip = {}, over = {}) => ({
  id: 1,
  width: 200,
  height: 100,
  ratio: 1,
  scroll: 0,
  zoom: 256,
  scrollY: 0,
  rulerHeight: 24,
  mode: "half",
  scale: "linear",
  gain: 1,
  palette,
  clipping: RED,
  rows: [
    {
      top: 0,
      height: 48,
      paletteIndex: 0,
      clips: [
        { id: "c1", media: "m1", start: 0, offset: 0, length: 100 * 256, muted: false, ...clip },
      ],
    },
  ],
  ...over,
});
const tileOf = (level) => () => {
  const tile = new Float32Array(TILE_PEAKS * 2);
  for (let i = 0; i < TILE_PEAKS; i += 1) {
    tile[2 * i] = -level;
    tile[2 * i + 1] = level;
  }
  return tile;
};
// The 1-px-wide rects are the bars: [name, x, y, 1, height].
const barsOf = (calls) => calls.filter((c) => c[0] === "rect" && c[3] === 1);
const heightAt = (calls, x) => barsOf(calls).find((c) => c[1] === x)?.[4];
const fills = (sets) => sets.filter((s) => s[0] === "fillStyle").map((s) => s[1]);

describe("waveform size follows gain", () => {
  test("0 dB draws exactly as before (no gain fields, same calls)", () => {
    const a = fakeContext();
    const b = fakeContext();
    paintWaveforms(a.ctx, job(), tileOf(0.5));
    paintWaveforms(b.ctx, job({ gainDb: 0, envelope: [] }), tileOf(0.5));
    assert.deepEqual(b.calls, a.calls);
    assert.equal(heightAt(a.calls, 10), 22);
  });

  test("-6 dB halves the bars, +6 dB doubles them (to the lane's top)", () => {
    const down = fakeContext();
    paintWaveforms(down.ctx, job({ gainDb: -6.0206 }), tileOf(0.5));
    assert.ok(Math.abs(heightAt(down.calls, 10) - 11) < 0.01);
    const up = fakeContext();
    paintWaveforms(up.ctx, job({ gainDb: 6.0206 }), tileOf(0.25));
    assert.ok(Math.abs(heightAt(up.calls, 10) - 22) < 0.01);
  });

  test("an envelope changes the height along the clip, in source frames", () => {
    const { ctx, calls } = fakeContext();
    // -12 dB at source frame 0 rising to 0 dB at frame 25600 (100 columns).
    paintWaveforms(
      ctx,
      job({
        envelope: [
          [0, -12],
          [25600, 0],
        ],
      }),
      tileOf(0.5),
    );
    const first = heightAt(calls, 0);
    const last = heightAt(calls, 99);
    assert.ok(first < 7 && last > 20, `${first} .. ${last}`);
  });

  test("the clip's offset slides the envelope window", () => {
    const { ctx, calls } = fakeContext();
    paintWaveforms(
      ctx,
      job({
        offset: 25600,
        envelope: [
          [0, -12],
          [25600, 0],
        ],
      }),
      tileOf(0.5),
    );
    assert.ok(Math.abs(heightAt(calls, 0) - 22) < 0.01, "flat at 0 dB past the last point");
  });

  test("the scale is capped as waveform_scale caps it (x32)", () => {
    const { ctx, calls } = fakeContext();
    paintWaveforms(ctx, job({ gainDb: 60 }), tileOf(0.001));
    // 0.001 * 32 = 0.032 of 44 px, not 0.001 * 1000.
    assert.ok(Math.abs(heightAt(calls, 5) - 0.032 * 44) < 0.01);
  });

  test("makeWaveformJob adds clip + track gain and the envelope, only when they say something", () => {
    const project = {
      rate: 48_000,
      media: [],
      buses: [],
      tracks: [
        {
          id: "t1",
          kind: "speech",
          gain_db: -2,
          pan: 0.5,
          muted: true,
          clips: [
            { id: "a", media: "m", start: 0, offset: 0, length: 1000, gain_db: 5, pan: -1 },
            {
              id: "b",
              media: "m",
              start: 0,
              offset: 0,
              length: 1000,
              envelope: [[0, 1]],
            },
          ],
        },
        { id: "t2", kind: "speech", clips: [{ id: "c", media: "m", start: 0, length: 1000 }] },
      ],
    };
    const state = {
      project,
      scroll: 0,
      zoom: 10,
      scrollY: 0,
      laneHeight: 48,
      waveformMode: "half",
      waveformScale: "linear",
    };
    const made = makeWaveformJob(state, { width: 400, height: 300, ratio: 1, id: 1 }, palette);
    const [a, b] = made.rows[0].clips;
    assert.equal(a.gainDb, 3, "clip 5 + track -2; pan and mute do not enter");
    assert.equal(b.gainDb, -2);
    assert.deepEqual(b.envelope, [[0, 1]]);
    assert.equal("gainDb" in made.rows[1].clips[0], false);
    assert.equal("envelope" in made.rows[1].clips[0], false);
  });
});

describe("clipping after gain is red", () => {
  test("a column over -0.1 dBFS after gain is drawn in the clipping colour, others in the wave colour", () => {
    const { ctx, sets } = fakeContext();
    const out = paintWaveforms(ctx, job({ gainDb: 7 }), tileOf(0.5));
    assert.ok(fills(sets).includes(RED));
    assert.ok(out.overs.c1 > 0);
  });

  test("the same material at 0 dB has no red and reports nothing", () => {
    const { ctx, sets } = fakeContext();
    const out = paintWaveforms(ctx, job(), tileOf(0.5));
    assert.ok(!fills(sets).includes(RED));
    assert.deepEqual(out.overs, {});
  });

  test("the over amount is the loudest column above full scale", () => {
    const { ctx } = fakeContext();
    const out = paintWaveforms(ctx, job({ gainDb: 12.0412 }), tileOf(0.5));
    assert.ok(Math.abs(out.overs.c1 - 6.0206) < 0.01);
  });

  test("only the columns that clip turn red (an envelope that rises into the red)", () => {
    const { ctx, calls, sets } = fakeContext();
    paintWaveforms(
      ctx,
      job({
        envelope: [
          [0, 0],
          [25600, 12],
        ],
      }),
      tileOf(0.5),
    );
    assert.ok(fills(sets).includes(RED));
    // Every bar is still drawn exactly once, in one of the two colours.
    assert.equal(barsOf(calls).length, 100);
  });

  test("a muted clip is not flagged", () => {
    const { ctx, sets } = fakeContext();
    const out = paintWaveforms(ctx, job({ gainDb: 12, muted: true }), tileOf(0.5));
    assert.ok(!fills(sets).includes(RED));
    assert.deepEqual(out.overs, {});
  });

  test("silence (a track at -inf encoded as a very low gain) never clips", () => {
    const { ctx } = fakeContext();
    const out = paintWaveforms(ctx, job({ gainDb: -200 }), tileOf(1));
    assert.deepEqual(out.overs, {});
  });

  test("works at a zoomed-out level too: a peak bucket holding one hot peak turns its column red", () => {
    const { ctx, sets } = fakeContext();
    const lookup = () => {
      const tile = new Float32Array(TILE_PEAKS * 2);
      tile[0] = -0.3;
      tile[1] = 0.6;
      return tile;
    };
    const out = paintWaveforms(ctx, job({ gainDb: 6 }, { zoom: 65536 }), lookup);
    assert.ok(fills(sets).includes(RED));
    assert.ok(out.overs.c1 >= 0);
  });
});
