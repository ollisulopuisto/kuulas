import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { quickMutePlan } from "../edit-plans.js";
import { DEFAULT_QUICK_MUTE_S, normaliseQuickMute, quickMuteStretch } from "../quick-mute.js";

const S = 48000;
const clip = (id, start, seconds, muted = false) => ({
  id,
  start: start * S,
  length: seconds * S,
  muted,
});
const state = (tracks, extra = {}) => ({
  project: { rate: S, tracks },
  selection: new Set(),
  focusTrack: "A",
  playhead: 5 * S,
  inPoint: null,
  outPoint: null,
  rangeMode: "all",
  trackSelection: new Set(),
  ...extra,
});
const two = () => [
  { id: "A", clips: [clip("a1", 0, 10)] },
  { id: "B", clips: [clip("b1", 0, 10)] },
];

describe("normaliseQuickMute", () => {
  test("defaults, clamps to 0.1-2.0", () => {
    assert.equal(normaliseQuickMute(null), DEFAULT_QUICK_MUTE_S);
    assert.equal(normaliseQuickMute("abc"), 0.5);
    assert.equal(normaliseQuickMute(0.01), 0.1);
    assert.equal(normaliseQuickMute("9"), 2);
    assert.equal(normaliseQuickMute("0.75"), 0.75);
  });
});

describe("quickMuteStretch", () => {
  test("is centred on the playhead", () => {
    assert.deepEqual(quickMuteStretch(5 * S, S, 0.5), {
      start: 5 * S - 0.25 * S,
      end: 5 * S + 0.25 * S,
    });
  });
  test("never starts before frame 0", () => {
    assert.equal(quickMuteStretch(100, S, 0.5).start, 0);
  });
});

describe("quickMutePlan", () => {
  test("one mute_range of 0.25 s each side on every track, by default", () => {
    const plan = quickMutePlan(state(two()));
    assert.equal(plan.op, "mute_range");
    assert.deepEqual(plan.args, {
      start: 5 * S - 0.25 * S,
      end: 5 * S + 0.25 * S,
      track_ids: ["A", "B"],
    });
  });
  test("uses the setting", () => {
    const plan = quickMutePlan(state(two(), { quickMuteS: 1 }));
    assert.equal(plan.args.end - plan.args.start, S);
  });
  test("selected tracks only: those tracks", () => {
    const plan = quickMutePlan(
      state(two(), { rangeMode: "selected", trackSelection: new Set(["B"]) }),
    );
    assert.deepEqual(plan.args.track_ids, ["B"]);
  });
  test("selected-only with none selected refuses with the scope message", () => {
    const plan = quickMutePlan(state(two(), { rangeMode: "selected" }));
    assert.equal(plan.refuse.key, "ui.scope.none_selected");
  });
  test("a set range does not change the stretch", () => {
    const plan = quickMutePlan(state(two(), { inPoint: 1 * S, outPoint: 3 * S }));
    assert.equal(plan.args.start, 5 * S - 0.25 * S);
  });
  test("nothing under the stretch: no plan", () => {
    assert.equal(quickMutePlan(state(two(), { playhead: 20 * S })), null);
  });
  test("no project: no plan", () => {
    assert.equal(quickMutePlan({ project: null, playhead: 0 }), null);
  });
  test("already fully muted: a notice, no edit", () => {
    const tracks = [{ id: "A", clips: [clip("m", 4.5, 1, true)] }];
    const plan = quickMutePlan(state(tracks));
    assert.equal(plan.op, undefined);
    assert.equal(plan.refuse.key, "ui.quick_mute.already");
  });
  test("partly muted: still sent", () => {
    const tracks = [{ id: "A", clips: [clip("m", 0, 5, true), clip("a2", 5, 5)] }];
    assert.equal(quickMutePlan(state(tracks)).op, "mute_range");
  });
  test("muted on one track but not another: sent", () => {
    const tracks = [
      { id: "A", clips: [clip("m", 0, 10, true)] },
      { id: "B", clips: [clip("b", 0, 10)] },
    ];
    assert.equal(quickMutePlan(state(tracks)).op, "mute_range");
  });
  test("near the clip start the stretch is still sent whole (ops clamps to the clip)", () => {
    const plan = quickMutePlan(state(two(), { playhead: 0.1 * S }));
    assert.equal(plan.args.start, 0);
    assert.equal(plan.args.end, Math.round(0.1 * S + 0.25 * S));
  });
});
