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

describe("transport: a stretch with an end (the candidate preview)", () => {
  function withHook() {
    const calls = [];
    let state = { playhead: 0, playing: false };
    const transport = createTransport({
      post: async (action, at, until) => {
        calls.push([action, at, until]);
        return { playing: action === "play", position: at ?? 0 };
      },
      getState: () => state,
      setState: (patch) => {
        state = { ...state, ...patch };
      },
      onError: () => {},
      onUserAction: () => calls.push(["user"]),
    });
    return { transport, calls };
  }

  test("playSegment plays from `at` to `until` and is not a user action", async () => {
    const { transport, calls } = withHook();
    await transport.playSegment(100, 300);
    assert.deepEqual(calls, [["play", 100, 300]]);
  });

  test("toggle, stop, seek and play tell the hook first: a preview in progress must end", async () => {
    const { transport, calls } = withHook();
    await transport.toggle();
    await transport.stop();
    await transport.seek(5);
    await transport.play(7);
    assert.deepEqual(calls.filter((call) => call[0] === "user").length, 4);
    assert.equal(calls[0][0], "user", "the hook comes before the request");
  });
});
