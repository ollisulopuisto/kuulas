import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createLoudnessLoader, readoutText, trackReadout } from "../loudness-readout.js";

const ready = (tracks, head = "h1") => ({ head, status: "ready", tracks });

describe("trackReadout", () => {
  test("nothing known or a failed measure shows nothing", () => {
    assert.equal(trackReadout(null, "t1").phase, "none");
    assert.equal(trackReadout({ head: "h", status: "failed", tracks: {} }, "t1").phase, "none");
  });

  test("a value with its target is tinted by the loudness rule", () => {
    const r = trackReadout(ready({ t1: { integrated: -21.3, target: -19 } }), "t1");
    assert.deepEqual(
      { phase: r.phase, state: r.state, stale: r.stale },
      { phase: "value", state: "notice", stale: false },
    );
    assert.equal(trackReadout(ready({ t1: { integrated: -20, target: -19 } }), "t1").state, "ok");
    assert.equal(trackReadout(ready({ t1: { integrated: -30, target: -19 } }), "t1").state, "warn");
  });

  test("no target: the value shows untinted", () => {
    const r = trackReadout(ready({ t1: { integrated: -21.3, target: null } }), "t1");
    assert.equal(r.phase, "value");
    assert.equal(r.state, "none");
  });

  test("a silent track (no integrated value) shows nothing", () => {
    assert.equal(
      trackReadout(ready({ t1: { integrated: null, target: -19 } }), "t1").phase,
      "none",
    );
  });

  test("a track the server did not report (no clips) shows nothing once ready", () => {
    assert.equal(trackReadout(ready({}), "t9").phase, "none");
  });

  test("while measuring: dots when there is no value yet, the old value marked stale", () => {
    assert.equal(trackReadout({ head: "h", status: "pending", tracks: {} }, "t1").phase, "pending");
    const r = trackReadout(
      { head: "h", status: "pending", tracks: { t1: { integrated: -19, target: -19 } } },
      "t1",
    );
    assert.equal(r.phase, "value");
    assert.equal(r.stale, true);
  });
});

describe("readoutText", () => {
  const num = (v, { digits = 0 } = {}) => v.toFixed(digits).replace("-", "−");
  const t = (key, vars) =>
    key === "ui.loudness.readout"
      ? `${vars.value} / ${vars.target} LUFS`
      : key === "ui.loudness.readout_no_target"
        ? `${vars.value} LUFS`
        : key;

  test("value with one decimal, a whole-number target without", () => {
    const r = trackReadout(ready({ t1: { integrated: -21.34, target: -19 } }), "t1");
    assert.equal(readoutText(r, num, t), "−21.3 / −19 LUFS");
  });

  test("a fractional target keeps its decimal", () => {
    const r = trackReadout(ready({ t1: { integrated: -21.34, target: -18.5 } }), "t1");
    assert.equal(readoutText(r, num, t), "−21.3 / −18.5 LUFS");
  });

  test("no target, pending, none", () => {
    const r = trackReadout(ready({ t1: { integrated: -21.34, target: null } }), "t1");
    assert.equal(readoutText(r, num, t), "−21.3 LUFS");
    assert.equal(readoutText({ phase: "pending" }, num, t), "…");
    assert.equal(readoutText({ phase: "none" }, num, t), "");
  });
});

// A manual clock: timers run when the test says so.
function clock() {
  const timers = new Map();
  let next = 1;
  return {
    setTimer: (fn, ms) => {
      timers.set(next, { fn, ms });
      return next++;
    },
    clearTimer: (id) => timers.delete(id),
    fire: () => {
      const all = [...timers.values()];
      timers.clear();
      for (const timer of all) timer.fn();
    },
    pending: () => timers.size,
    delays: () => [...timers.values()].map((t) => t.ms),
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
}

const body = (id, integrated) => ({ tracks: [{ track_id: id, integrated, target_lufs: -19 }] });

describe("createLoudnessLoader", () => {
  function make(fetchCurve) {
    const c = clock();
    const patches = [];
    const loader = createLoudnessLoader({
      fetchCurve,
      onChange: (p) => patches.push(p),
      delayMs: 700,
      setTimer: c.setTimer,
      clearTimer: c.clearTimer,
    });
    return { c, patches, loader };
  }
  const last = (patches) => patches[patches.length - 1];

  test("nothing is asked until the project has settled, and edits restart the wait", () => {
    let calls = 0;
    const { c, loader } = make(() => {
      calls += 1;
      return Promise.resolve(body("t1", -20));
    });
    loader.settle("h1");
    loader.settle("h2");
    loader.settle("h3");
    assert.equal(calls, 0);
    assert.equal(c.pending(), 1);
    c.fire();
    assert.equal(calls, 1);
  });

  test("pending is announced at once, ready with the tracks keyed by id", async () => {
    const { c, patches, loader } = make(() => Promise.resolve(body("t1", -20.4)));
    loader.settle("h1");
    assert.equal(last(patches).loudness.status, "pending");
    c.fire();
    await new Promise((r) => setImmediate(r));
    const got = last(patches).loudness;
    assert.equal(got.status, "ready");
    assert.equal(got.head, "h1");
    assert.deepEqual(got.tracks.t1, { integrated: -20.4, target: -19 });
  });

  test("a stale answer is dropped and its request cancelled", async () => {
    const first = deferred();
    const second = deferred();
    const queue = [first, second];
    const signals = [];
    const { c, patches, loader } = make((signal) => {
      signals.push(signal);
      return queue.shift().promise;
    });
    loader.settle("h1");
    c.fire();
    loader.settle("h2");
    assert.equal(signals[0].aborted, true);
    c.fire();
    second.resolve(body("t1", -18));
    first.resolve(body("t1", -30));
    await new Promise((r) => setImmediate(r));
    const got = last(patches).loudness;
    assert.equal(got.head, "h2");
    assert.equal(got.tracks.t1.integrated, -18);
  });

  test("a head seen before is served from the cache without asking again", async () => {
    let calls = 0;
    const { c, patches, loader } = make(() => {
      calls += 1;
      return Promise.resolve(body("t1", -20));
    });
    loader.settle("h1");
    c.fire();
    await new Promise((r) => setImmediate(r));
    loader.settle("h2");
    c.fire();
    await new Promise((r) => setImmediate(r));
    loader.settle("h1"); // undo
    assert.equal(c.pending(), 0);
    assert.equal(calls, 2);
    assert.equal(last(patches).loudness.head, "h1");
    assert.equal(last(patches).loudness.status, "ready");
  });

  test("a failure shows nothing, is not cached and is asked again only after a back-off", async () => {
    let calls = 0;
    const { c, patches, loader } = make(() => {
      calls += 1;
      return Promise.reject(new Error("boom"));
    });
    const flush = () => new Promise((r) => setImmediate(r));
    loader.settle("h1");
    c.fire();
    await flush();
    assert.equal(last(patches).loudness.status, "failed");
    // Every store change settles again: none of them may ask at once (each ask
    // used to start an analysis process; owner's ps, 2026-10-20).
    for (let i = 0; i < 20; i += 1) loader.settle("h1");
    assert.equal(calls, 1);
    const waits = [];
    for (let i = 0; i < 4; i += 1) {
      waits.push(c.delays()[0]);
      c.fire();
      await flush();
    }
    assert.equal(calls, 5);
    assert.deepEqual(waits, [5000, 10000, 20000, 40000]);
  });

  test("an edit after a failure waits out the back-off too", async () => {
    let calls = 0;
    const { c, loader } = make(() => {
      calls += 1;
      return Promise.reject(new Error("boom"));
    });
    loader.settle("h1");
    c.fire();
    await new Promise((r) => setImmediate(r));
    loader.settle("h2");
    assert.deepEqual(c.delays(), [5000]); // the back-off's retry, no new ask
    c.fire();
    assert.equal(calls, 2);
  });

  test("a success resets the back-off", async () => {
    let fail = true;
    const { c, loader } = make(() =>
      fail ? Promise.reject(new Error("boom")) : Promise.resolve(body("t1", -20)),
    );
    const flush = () => new Promise((r) => setImmediate(r));
    loader.settle("h1");
    c.fire();
    await flush();
    fail = false;
    c.fire(); // the retry succeeds
    await flush();
    loader.settle("h2");
    assert.deepEqual(c.delays(), [700]);
  });

  test("settling on the head already shown or being asked changes nothing", async () => {
    const { c, patches, loader } = make(() => Promise.resolve(body("t1", -20)));
    loader.settle("h1");
    c.fire();
    await new Promise((r) => setImmediate(r));
    const n = patches.length;
    loader.settle("h1");
    assert.equal(patches.length, n);
    assert.equal(c.pending(), 0);
  });

  test("no head (no project) is ignored", () => {
    const { c, patches, loader } = make(() => Promise.resolve(body("t1", -20)));
    loader.settle(null);
    assert.equal(patches.length, 0);
    assert.equal(c.pending(), 0);
  });
});
