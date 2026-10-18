import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createTransport } from "../transport.js";

// What the transport sends the engine for fast listening (WP26); nothing plays.
function harness(initial = {}) {
  let state = {
    project: { tracks: [] },
    playhead: 100,
    playing: false,
    speed: 1,
    loop: false,
    inPoint: null,
    outPoint: null,
    fast: { fast: 1.35, active: true },
    ...initial,
  };
  const calls = [];
  const transport = createTransport({
    post: async (action, at, _until, _skip, options) => {
      calls.push({ action, at, options });
      return { playing: action !== "stop", position: at ?? 0 };
    },
    getState: () => state,
    setState: (p) => {
      state = { ...state, ...p };
    },
    onError: (e) => calls.push({ error: e.message }),
  });
  return { transport, calls };
}

const on = (fast) => ({ fast, active: true });
const off = (fast) => ({ fast, active: false });

describe("fast listening in the transport", () => {
  test("play carries the chosen speed, pitch kept, while fast listening is on", async () => {
    const h = harness();
    await h.transport.toggle();
    assert.deepEqual(h.calls, [
      { action: "play", at: 100, options: { speed: 1.35, preserve_pitch: true } },
    ]);
  });
  test("off, play has no speed field", async () => {
    const h = harness({ fast: off(1.35) });
    await h.transport.toggle();
    assert.equal(h.calls[0].options, undefined);
  });
  test("switching on while playing restarts from the playhead at the chosen speed", async () => {
    const h = harness({ playing: true, playhead: 500 });
    await h.transport.fastChanged(off(1.35), on(1.35));
    assert.deepEqual(h.calls, [
      { action: "play", at: 500, options: { speed: 1.35, preserve_pitch: true } },
    ]);
  });
  test("switching off while playing plays on at normal speed", async () => {
    const h = harness({ playing: true, playhead: 500, speed: 1.35, fast: off(1.35) });
    await h.transport.fastChanged(on(1.35), off(1.35));
    assert.deepEqual(h.calls, [{ action: "play", at: 500, options: undefined }]);
  });
  test("nudging while it plays fast retunes the run, with no restart", async () => {
    const h = harness({ playing: true, speed: 1.35, fast: on(1.4) });
    await h.transport.fastChanged(on(1.35), on(1.4));
    assert.deepEqual(h.calls, [{ action: "rate", at: null, options: { speed: 1.4 } }]);
  });
  test("a held key nudges again before the engine has answered", async () => {
    const h = harness({ playing: true, speed: 1.35, fast: on(1.5) });
    await h.transport.fastChanged(on(1.45), on(1.5));
    assert.equal(h.calls.length, 1);
  });
  test("stopped, or switched off, a nudge sends nothing", async () => {
    const stopped = harness();
    await stopped.transport.fastChanged(on(1.3), on(1.35));
    const idle = harness({ playing: true, fast: off(1.35) });
    await idle.transport.fastChanged(off(1.3), off(1.35));
    assert.deepEqual([...stopped.calls, ...idle.calls], []);
  });
  test("a loop and fast listening go in the same request", async () => {
    const h = harness({ loop: true, inPoint: 1000, outPoint: 5000 });
    await h.transport.toggle();
    assert.deepEqual(h.calls[0].options, {
      loop: [1000, 5000],
      speed: 1.35,
      preserve_pitch: true,
    });
  });
});
