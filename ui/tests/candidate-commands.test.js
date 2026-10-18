import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { markPlan, registerCandidateCommands } from "../candidate-commands.js";
import { createRegistry } from "../commands.js";

const row = (id, start, extra = {}) => ({
  id,
  kind: "silence",
  state: "open",
  start,
  end: start + 100,
  spans: [[start, start + 100]],
  tracks: ["a"],
  seconds: 2,
  ...extra,
});
const project = { rate: 100, tracks: [{ id: "a", clips: [{ start: 0, length: 5000 }] }] };
const base = {
  project,
  playhead: 0,
  inPoint: null,
  outPoint: null,
  focusTrack: "a",
  candidates: [row("x", 200), row("y", 500)],
  candidateCurrent: null,
  candidatesOpenOnly: true,
  candidateMarkStart: null,
  candidateBusy: false,
};

function setup(overrides = {}) {
  const state = { ...base, ...overrides };
  const calls = [];
  const registry = createRegistry();
  registerCandidateCommands(registry, {
    t: (key, values) => `${key}${values ? JSON.stringify(values) : ""}`,
    app: {
      getState: () => state,
      patch: (patch) => {
        Object.assign(state, patch);
        calls.push(["patch", patch]);
      },
      selectCandidate: (r) => calls.push(["select", r.id]),
      findCandidates: () => calls.push(["find"]),
      applyCandidate: (id, mode) => calls.push(["apply", id, mode]),
      keepCandidate: (id) => calls.push(["keep", id]),
      markCandidate: (start, end, track) => calls.push(["mark", start, end, track]),
      previewCandidate: (r) => calls.push(["preview", r.id]),
      toast: (text) => calls.push(["toast", text]),
    },
  });
  return { registry, state, calls };
}

describe("stepping", () => {
  test("next and previous select the neighbour", () => {
    const { registry, state, calls } = setup({ playhead: 0 });
    assert.equal(registry.run("candidate.next", null, state), true);
    assert.deepEqual(calls, [["select", "x"]]);
  });
  test("at the end of the list next cannot run", () => {
    const { registry, state } = setup({ playhead: 900 });
    assert.equal(registry.can("candidate.next", state), false);
    assert.equal(registry.can("candidate.previous", state), true);
  });
  test("Open only decides which ones are visited", () => {
    const { registry, state, calls } = setup({
      candidates: [row("x", 200, { state: "kept" }), row("y", 500)],
    });
    registry.run("candidate.next", null, state);
    assert.deepEqual(calls, [["select", "y"]]);
    state.candidatesOpenOnly = false;
    state.playhead = 0;
    registry.run("candidate.next", null, state);
    assert.deepEqual(calls.at(-1), ["select", "x"]);
  });
});

describe("deciding", () => {
  test("Enter applies the current candidate as a soft cut", () => {
    const { registry, state, calls } = setup({ candidateCurrent: "x" });
    registry.run("candidate.apply", { target: { tagName: "LI" } }, state);
    assert.deepEqual(calls, [["apply", "x", "soft"]]);
  });
  test("Enter on a focused button presses that button instead", () => {
    const { registry, state, calls } = setup({ candidateCurrent: "x" });
    let clicked = 0;
    registry.run(
      "candidate.apply",
      { target: { tagName: "BUTTON", click: () => clicked++ } },
      state,
    );
    assert.equal(clicked, 1);
    assert.deepEqual(calls, []);
  });
  test("Cut and close gap is its own command, a ripple", () => {
    const { registry, state, calls } = setup({ candidateCurrent: "y" });
    registry.run("candidate.apply_ripple", null, state);
    assert.deepEqual(calls, [["apply", "y", "ripple"]]);
  });
  test("K keeps it", () => {
    const { registry, state, calls } = setup({ candidateCurrent: "y" });
    registry.run("candidate.reject", null, state);
    assert.deepEqual(calls, [["keep", "y"]]);
  });
  test("nothing current, or one already decided: they cannot run", () => {
    const none = setup();
    for (const id of ["candidate.apply", "candidate.apply_ripple", "candidate.reject"]) {
      assert.equal(none.registry.can(id, none.state), false, id);
    }
    const done = setup({
      candidateCurrent: "x",
      candidates: [row("x", 200, { state: "cut" })],
    });
    for (const id of ["candidate.apply", "candidate.apply_ripple", "candidate.reject"]) {
      assert.equal(done.registry.can(id, done.state), false, id);
    }
  });
  test("preview works on an open candidate that is on the timeline", () => {
    const { registry, state, calls } = setup({ candidateCurrent: "x" });
    registry.run("candidate.preview", null, state);
    assert.deepEqual(calls, [["preview", "x"]]);
    const gone = setup({ candidateCurrent: "g", candidates: [row("g", null)] });
    assert.equal(gone.registry.can("candidate.preview", gone.state), false);
  });
});

describe("the filter and finding", () => {
  test("the filter toggles Open only", () => {
    const { registry, state, calls } = setup();
    registry.run("candidate.filter", null, state);
    assert.deepEqual(calls, [["patch", { candidatesOpenOnly: false }]]);
  });
  test("find runs once at a time", () => {
    const { registry, state, calls } = setup();
    registry.run("candidate.find", null, state);
    assert.deepEqual(calls, [["find"]]);
    state.candidateBusy = true;
    assert.equal(registry.can("candidate.find", state), false);
  });
});

describe("markPlan: D", () => {
  test("in and out set: that range, on the current track", () => {
    assert.deepEqual(markPlan({ ...base, inPoint: 300, outPoint: 450 }), {
      action: "mark",
      start: 300,
      end: 450,
      track: "a",
    });
  });
  test("no range: the first press starts at the playhead, the second ends there", () => {
    assert.deepEqual(markPlan({ ...base, playhead: 1000 }), { action: "begin", at: 1000 });
    assert.deepEqual(markPlan({ ...base, playhead: 1250, candidateMarkStart: 1000 }), {
      action: "mark",
      start: 1000,
      end: 1250,
      track: "a",
    });
  });
  test("the second press before the first: the range is the other way round", () => {
    const plan = markPlan({ ...base, playhead: 800, candidateMarkStart: 1000 });
    assert.equal(plan.start, 800);
    assert.equal(plan.end, 1000);
  });
  test("the same instant twice: start again", () => {
    assert.deepEqual(markPlan({ ...base, playhead: 1000, candidateMarkStart: 1000 }), {
      action: "begin",
      at: 1000,
    });
  });
  test("a track with no clip there is not named: the server picks one", () => {
    const state = {
      ...base,
      playhead: 9000,
      project: { rate: 100, tracks: [{ id: "a", clips: [{ start: 0, length: 100 }] }] },
    };
    assert.equal(markPlan({ ...state, inPoint: 9000, outPoint: 9500 }).track, null);
  });
});

describe("D and Alt+D commands", () => {
  test("D begins, then marks, and tells the user", () => {
    const { registry, state, calls } = setup({ playhead: 1000 });
    registry.run("candidate.mark", null, state);
    assert.deepEqual(calls[0], ["patch", { candidateMarkStart: 1000 }]);
    assert.equal(calls[1][0], "toast");
    state.playhead = 1300;
    registry.run("candidate.mark", null, state);
    assert.deepEqual(calls.at(-1), ["mark", 1000, 1300, "a"]);
    assert.deepEqual(calls.at(-2), ["patch", { candidateMarkStart: null }]);
  });
  test("Alt+D needs in and out", () => {
    const { registry, state, calls } = setup();
    assert.equal(registry.can("candidate.mark_range", state), false);
    state.inPoint = 100;
    state.outPoint = 400;
    registry.run("candidate.mark_range", null, state);
    assert.deepEqual(calls, [["mark", 100, 400, "a"]]);
  });
});
