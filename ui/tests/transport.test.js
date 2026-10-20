import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createTransport } from "../transport.js";

// A fake engine: the same contract as POST /api/transport and the live channel's
// position messages, without audio. Nothing here plays through a speaker.
function fakeEngine() {
  const engine = { playing: false, position: 0, calls: [] };
  engine.post = async (action, at) => {
    engine.calls.push([action, at]);
    if (action === "play") {
      if (at !== null && at !== undefined) engine.position = at;
      engine.playing = true;
    } else if (action === "stop") engine.playing = false;
    else if (action === "seek") engine.position = at;
    return { playing: engine.playing, position: engine.position };
  };
  return engine;
}

function harness(initial = {}) {
  let state = { playhead: 0, playing: false, ...initial };
  const engine = fakeEngine();
  const errors = [];
  const transport = createTransport({
    post: engine.post,
    getState: () => state,
    setState: (patch) => {
      state = { ...state, ...patch };
    },
    onError: (e) => errors.push(e),
  });
  return { engine, transport, errors, state: () => state };
}

describe("transport", () => {
  test("Space plays from the playhead and the answer sets the state", async () => {
    const h = harness({ playhead: 4800 });
    await h.transport.toggle();
    assert.deepEqual(h.engine.calls, [["play", 4800]]);
    assert.equal(h.state().playing, true);
  });

  test("Space again stops, and the playhead stays where the engine stopped", async () => {
    const h = harness({ playhead: 100 });
    await h.transport.toggle();
    h.engine.position = 777;
    await h.transport.toggle();
    assert.deepEqual(h.engine.calls.at(-1), ["stop", null]);
    assert.equal(h.state().playing, false);
    assert.equal(h.state().playhead, 777);
  });

  test("Space while playing stops the cursor at once, then lands on the engine's frame", async () => {
    let state = { playhead: 0, playing: true };
    const seen = [];
    let answer;
    const transport = createTransport({
      post: () =>
        new Promise((resolve) => {
          answer = resolve;
        }),
      getState: () => state,
      setState: (patch) => {
        state = { ...state, ...patch };
        seen.push(patch);
      },
      onError: () => {},
      freeze: () => 5000, // the playhead clock's frame this instant
      settle: (status) => seen.push({ settled: status.position }),
    });
    const pending = transport.toggle();
    assert.deepEqual(state, { playhead: 5000, playing: false, speed: 1 }); // before any answer
    answer({ playing: false, position: 4990 });
    await pending;
    assert.equal(state.playhead, 4990);
    assert.ok(seen.some((x) => x.settled === 4990));
  });

  test("seeking moves the playhead on screen before the engine answers", async () => {
    const h = harness();
    const pending = h.transport.seek(2400);
    assert.equal(h.state().playhead, 2400);
    await pending;
    assert.deepEqual(h.engine.calls, [["seek", 2400]]);
  });

  test("a negative seek goes to the start", async () => {
    const h = harness();
    await h.transport.seek(-50);
    assert.equal(h.state().playhead, 0);
  });

  test("a failed play (no device) is reported and nothing is left playing", async () => {
    const h = harness();
    const failing = createTransport({
      post: async () => {
        throw new Error("no audio device");
      },
      getState: h.state,
      setState: () => {},
      onError: (e) => h.errors.push(e),
    });
    await failing.toggle();
    assert.equal(h.errors[0].message, "no audio device");
    assert.equal(h.state().playing, false);
  });
});

describe("transport: the candidate preview", () => {
  test("preview plays `at` to `until` skipping the ranges, in one request", async () => {
    const calls = [];
    let state = { playhead: 0, playing: false };
    const transport = createTransport({
      post: async (action, at, until, skip) => {
        calls.push([action, at, until, skip]);
        return { playing: true, position: 120 };
      },
      getState: () => state,
      setState: (patch) => {
        state = { ...state, ...patch };
      },
      onError: () => {},
    });
    await transport.preview(100, 300, [[150, 200]]);
    assert.deepEqual(calls, [["play", 100, 300, [[150, 200]]]]);
    assert.deepEqual(state, { playhead: 120, playing: true, speed: 1 });
  });

  test("a refused preview is reported like any failed play", async () => {
    const errors = [];
    const transport = createTransport({
      post: async () => {
        throw new Error("A range to skip must be two frame numbers");
      },
      getState: () => ({ playhead: 0, playing: false }),
      setState: () => {},
      onError: (e) => errors.push(e.message),
    });
    await transport.preview(0, 10, [[5, 1]]);
    assert.equal(errors.length, 1);
  });
});

describe("transport: the JKL shuttle", () => {
  // The fake engine answers like the real one: the speed it was asked for while playing.
  function shuttleHarness(initial = {}) {
    let state = { playhead: 0, playing: false, speed: 1, ...initial };
    const calls = [];
    const engine = { speed: 1, playing: false, position: 0 };
    const transport = createTransport({
      post: async (action, at, until, skip, options) => {
        calls.push([action, at, until, skip, options ?? null]);
        if (action === "play") {
          engine.playing = true;
          engine.speed = options?.speed ?? 1;
          if (at !== null) engine.position = at;
        } else if (action === "stop") {
          engine.playing = false;
          engine.speed = 1;
        }
        return { playing: engine.playing, position: engine.position, speed: engine.speed };
      },
      getState: () => state,
      setState: (patch) => {
        state = { ...state, ...patch };
      },
      onError: () => {},
    });
    return { transport, calls, state: () => state, engine };
  }

  test("L from a stop plays forward at 1x from the playhead, pitch not kept", async () => {
    const h = shuttleHarness({ playhead: 4800 });
    await h.transport.shuttle(1);
    assert.deepEqual(h.calls, [["play", 4800, null, null, { speed: 1, preserve_pitch: false }]]);
    assert.equal(h.state().playing, true);
    assert.equal(h.state().speed, 1);
  });

  test("a faster speed starts from the live playhead and the state mirrors the engine", async () => {
    const h = shuttleHarness({ playhead: 9000, playing: true });
    await h.transport.shuttle(-2);
    assert.deepEqual(h.calls[0].slice(0, 2), ["play", 9000]);
    assert.equal(h.state().speed, -2);
  });

  test("speed 0 stops, and the state is back to 1x", async () => {
    const h = shuttleHarness({ playhead: 100 });
    await h.transport.shuttle(3);
    await h.transport.shuttle(0);
    assert.equal(h.calls.at(-1)[0], "stop");
    assert.equal(h.state().playing, false);
    assert.equal(h.state().speed, 1);
  });

  test("Space, stop and the candidate preview reset the speed to 1x", async () => {
    const h = shuttleHarness({ playhead: 100 });
    await h.transport.shuttle(2);
    await h.transport.toggle();
    assert.equal(h.state().speed, 1);
    await h.transport.shuttle(2);
    await h.transport.preview(10, 20, []);
    assert.equal(h.state().speed, 1);
    await h.transport.shuttle(2);
    await h.transport.play(0);
    assert.equal(h.state().speed, 1);
  });

  test("a seek keeps whatever speed the engine answers with", async () => {
    const h = shuttleHarness({ playhead: 100 });
    await h.transport.shuttle(2);
    await h.transport.seek(500);
    assert.equal(h.state().speed, 2);
  });

  test("pressing L, L, J, K walks the ladder from what the engine is doing", async () => {
    const h = shuttleHarness({ playhead: 0 });
    const speeds = [];
    for (const key of ["l", "l", "l", "j", "k"]) {
      await h.transport.press(key);
      speeds.push(h.state().playing ? h.state().speed : 0);
    }
    assert.deepEqual(speeds, [1, 1.5, 2, -1, 0]);
  });

  test("Space-started playback at 1x goes to 1.5x on L", async () => {
    const h = shuttleHarness({ playhead: 0 });
    await h.transport.toggle();
    await h.transport.press("l");
    assert.equal(h.state().speed, 1.5);
  });

  test("quick presses climb the ladder without waiting for the engine's answers", async () => {
    const h = shuttleHarness({ playhead: 0 });
    await Promise.all(["l", "l", "l"].map((key) => h.transport.press(key)));
    assert.deepEqual(
      h.calls.map((call) => call[4].speed),
      [1, 1.5, 2],
    );
    assert.equal(h.state().speed, 2);
  });

  test("a failed shuttle changes nothing", async () => {
    const errors = [];
    let state = { playhead: 0, playing: false, speed: 1 };
    const transport = createTransport({
      post: async () => {
        throw new Error("no audio device");
      },
      getState: () => state,
      setState: (p) => {
        state = { ...state, ...p };
      },
      onError: (e) => errors.push(e.message),
    });
    await transport.shuttle(2);
    assert.deepEqual(errors, ["no audio device"]);
    assert.deepEqual(state, { playhead: 0, playing: false, speed: 1 });
  });
});

describe("loop playback", () => {
  function loopHarness(initial = {}) {
    let state = {
      project: { tracks: [] },
      playhead: 100,
      playing: false,
      loop: true,
      inPoint: 1000,
      outPoint: 5000,
      ...initial,
    };
    const calls = [];
    const transport = createTransport({
      post: async (action, at, _until, _skip, options) => {
        calls.push({ action, at, options });
        return { playing: action === "play", position: at ?? 0 };
      },
      getState: () => state,
      setState: (p) => {
        state = { ...state, ...p };
      },
      onError: (e) => calls.push({ error: e.message }),
    });
    return {
      transport,
      calls,
      set: (p) => {
        state = { ...state, ...p };
      },
    };
  }

  test("Space with the loop on sends the loop range", async () => {
    const h = loopHarness();
    await h.transport.toggle();
    assert.deepEqual(h.calls, [{ action: "play", at: 100, options: { loop: [1000, 5000] } }]);
  });
  test("without the loop, or without a range, play has no loop field", async () => {
    const off = loopHarness({ loop: false });
    await off.transport.toggle();
    const none = loopHarness({ inPoint: null, outPoint: null });
    await none.transport.toggle();
    assert.equal(off.calls[0].options, undefined);
    assert.equal(none.calls[0].options, undefined);
  });
  test("resendLoop plays on from the playhead with the new range, never stopping", async () => {
    const h = loopHarness({ playing: true, playhead: 2000 });
    h.set({ outPoint: 8000 });
    await h.transport.resendLoop();
    assert.deepEqual(h.calls, [{ action: "play", at: 2000, options: { loop: [1000, 8000] } }]);
  });
  test("resendLoop does nothing while stopped", async () => {
    const h = loopHarness();
    await h.transport.resendLoop();
    assert.deepEqual(h.calls, []);
  });
});

describe("quick seeks (owner, 2026-10-19: Alt+arrow pressed many times made the cursor jerk back)", () => {
  test("an older seek's answer arriving late does not move the playhead back", async () => {
    let state = { playhead: 0, playing: false };
    const waiting = [];
    const transport = createTransport({
      post: (_action, at) =>
        new Promise((resolve) => waiting.push(() => resolve({ playing: false, position: at }))),
      getState: () => state,
      setState: (patch) => {
        state = { ...state, ...patch };
      },
      onError: () => {},
    });
    const first = transport.seek(480);
    const second = transport.seek(960);
    const third = transport.seek(1440);
    assert.equal(state.playhead, 1440); // on screen at once
    waiting[2](); // the newest answer arrives first
    await third;
    waiting[0](); // then the oldest one, late
    await first;
    waiting[1]();
    await second;
    assert.equal(state.playhead, 1440);
  });

  test("a single seek still takes the engine's answer", async () => {
    const h = harness();
    h.engine.position = 0;
    await h.transport.seek(2400);
    assert.equal(h.state().playhead, 2400);
  });

  test("a play after a seek is not dropped", async () => {
    const h = harness();
    await h.transport.seek(2400);
    await h.transport.toggle();
    assert.equal(h.state().playing, true);
  });
});
