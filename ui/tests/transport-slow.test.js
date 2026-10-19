import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createTransport } from "../transport.js";

describe("slow hold-to-play in the transport", () => {
  test("slowStart plays from the playhead at the signed speed, tape-style; slowStop stops", async () => {
    const calls = [];
    let state = { playhead: 9600, playing: false };
    const transport = createTransport({
      post: async (action, at, _until, _skip, options) => {
        calls.push([action, at, options ?? null]);
        return { playing: action === "play", position: at ?? 9000, speed: options?.speed };
      },
      getState: () => state,
      setState: (patch) => {
        state = { ...state, ...patch };
      },
      onError: () => {},
    });
    await transport.slowStart(-0.5);
    assert.deepEqual(calls[0], ["play", 9600, { speed: -0.5, preserve_pitch: false }]);
    await transport.slowStop();
    assert.equal(calls[1][0], "stop");
    assert.equal(state.playing, false);
  });

  test("a stop queued right after the start goes out after it", async () => {
    const order = [];
    const transport = createTransport({
      post: async (action) => {
        await new Promise((r) => setTimeout(r, action === "play" ? 20 : 0));
        order.push(action);
        return { playing: action === "play", position: 0 };
      },
      getState: () => ({ playhead: 0, playing: false }),
      setState: () => {},
      onError: () => {},
    });
    const a = transport.slowStart(0.5);
    const b = transport.slowStop();
    await Promise.all([a, b]);
    assert.deepEqual(order, ["play", "stop"]);
  });
});
