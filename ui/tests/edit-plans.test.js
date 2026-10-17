import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  changedTracks,
  createBurst,
  cutPlan,
  deletePlan,
  gainPlan,
  mutePlan,
  nudgePlan,
  soloPlan,
  splitPlan,
  trackMutePlan,
  trimPlan,
} from "../edit-plans.js";

const S = 48000;
const clip = (id, start, seconds, extra = {}) => ({
  id,
  start: start * S,
  length: seconds * S,
  muted: false,
  ...extra,
});
const project = {
  rate: S,
  tracks: [
    { id: "A", mute: false, solo: false, clips: [clip("a1", 0, 10), clip("a2", 12, 8)] },
    { id: "V", mute: true, solo: false, clips: [clip("v1", 0, 10)] },
    { id: "M", mute: false, solo: false, clips: [] },
  ],
};
const state = (extra = {}) => ({
  project,
  selection: new Set(),
  focusTrack: "A",
  focusBus: null,
  playhead: 4 * S,
  inPoint: null,
  outPoint: null,
  groupEditing: true,
  nudgeMs: 10,
  ...extra,
});
const range = { inPoint: 2 * S, outPoint: 6 * S };

describe("split", () => {
  test("B splits the current track's clip under the playhead", () => {
    const plan = splitPlan(state());
    assert.equal(plan.op, "split_clips");
    assert.deepEqual(plan.args, { at: 4 * S, clip_ids: ["a1"] });
    assert.equal(plan.toast.values.count, 1);
  });
  test("with clips selected, B splits those that hold the playhead", () => {
    const plan = splitPlan(state({ selection: new Set(["v1", "a2"]), focusTrack: "M" }));
    assert.deepEqual(plan.args.clip_ids, ["v1"]);
  });
  test("Shift+B splits every track at the playhead", () => {
    assert.deepEqual(splitPlan(state(), { all: true }).args.clip_ids, ["a1", "v1"]);
  });
  test("nothing under the playhead: nothing to do", () => {
    assert.equal(splitPlan(state({ playhead: 11 * S })), null);
    assert.equal(splitPlan(state({ focusTrack: "M" })), null);
    assert.equal(splitPlan(state({ project: null })), null);
  });
});

describe("delete (soft cut, gap kept)", () => {
  test("the range is muted in place on the current track, with the group when on", () => {
    const plan = deletePlan(state(range));
    assert.equal(plan.op, "mute_range");
    assert.deepEqual(plan.args, {
      start: 2 * S,
      end: 6 * S,
      track_ids: ["A"],
      group_editing: true,
    });
    assert.equal(plan.toast.values.seconds, 4);
  });
  test("group editing off is passed on", () => {
    assert.equal(deletePlan(state({ ...range, groupEditing: false })).args.group_editing, false);
  });
  test("selected clips are muted, with no clipboard and no range needed", () => {
    const plan = deletePlan(state({ selection: new Set(["a1", "v1"]) }));
    assert.equal(plan.op, "set_clips");
    assert.deepEqual(plan.args, { clip_ids: ["a1", "v1"], muted: true });
  });
  test("a range wins over a selection", () => {
    assert.equal(deletePlan(state({ ...range, selection: new Set(["a1"]) })).op, "mute_range");
  });
  test("nothing selected and no range: nothing to do; already-muted clips too", () => {
    assert.equal(deletePlan(state()), null);
    const muted = {
      ...project,
      tracks: [{ id: "A", clips: [clip("a1", 0, 10, { muted: true })] }],
    };
    assert.equal(deletePlan(state({ project: muted, selection: new Set(["a1"]) })), null);
  });
  test("a range with no current track has nowhere to act", () => {
    assert.equal(deletePlan(state({ ...range, focusTrack: null })), null);
  });
});

describe("cut (ripple)", () => {
  test("the range, on the current track plus the group when group editing is on", () => {
    const plan = cutPlan(state(range));
    assert.equal(plan.op, "cut_range");
    assert.deepEqual(plan.args, {
      start: 2 * S,
      end: 6 * S,
      track_ids: ["A"],
      group_editing: true,
    });
    assert.equal(plan.toast.tracks, true);
  });
  test("Shift+X never takes the group along", () => {
    assert.equal(cutPlan(state(range), { thisTrackOnly: true }).args.group_editing, false);
  });
  test("selected clips: their span, on their tracks", () => {
    const plan = cutPlan(state({ selection: new Set(["a2", "v1"]) }));
    assert.deepEqual(plan.args, {
      start: 0,
      end: 20 * S,
      track_ids: ["A", "V"],
      group_editing: true,
    });
  });
  test("nothing to cut", () => {
    assert.equal(cutPlan(state()), null);
  });
});

describe("mute clips (N)", () => {
  test("mutes the selection; if all are muted already, unmutes", () => {
    assert.deepEqual(mutePlan(state({ selection: new Set(["a1"]) })).args, {
      clip_ids: ["a1"],
      muted: true,
    });
    const allMuted = {
      ...project,
      tracks: [{ id: "A", clips: [clip("a1", 0, 10, { muted: true })] }],
    };
    const plan = mutePlan(state({ project: allMuted, selection: new Set(["a1"]) }));
    assert.equal(plan.args.muted, false);
  });
  test("no selection: nothing", () => {
    assert.equal(mutePlan(state()), null);
  });
});

describe("trim (Q, W)", () => {
  test("Q trims the start of the clip under the playhead on the current track", () => {
    const plan = trimPlan(state(), "start");
    assert.equal(plan.op, "trim_clips");
    assert.deepEqual(plan.args, { clip_ids: ["a1"], start: 4 * S });
  });
  test("W trims the end of the selected clips that hold the playhead", () => {
    const plan = trimPlan(state({ selection: new Set(["a1", "v1", "a2"]) }), "end");
    assert.deepEqual(plan.args, { clip_ids: ["a1", "v1"], end: 4 * S });
  });
  test("playhead outside every candidate: nothing", () => {
    assert.equal(trimPlan(state({ playhead: 11 * S }), "start"), null);
  });
});

describe("nudge", () => {
  test("by the nudge step, later or earlier, with the group when on", () => {
    const plan = nudgePlan(state({ selection: new Set(["a1"]) }), 1);
    assert.equal(plan.op, "nudge_clips");
    assert.deepEqual(plan.args, { clip_ids: ["a1"], delta: 480, group_editing: true });
    assert.equal(nudgePlan(state({ selection: new Set(["a1"]) }), -1).args.delta, -480);
  });
  test("needs a selection", () => {
    assert.equal(nudgePlan(state(), 1), null);
  });
});

describe("clip gain", () => {
  test("0.5 dB per press; presses in one burst share a key and add up", () => {
    const burst = createBurst(600);
    const selection = new Set(["a1", "v1"]);
    const first = gainPlan(state({ selection }), 1, burst.key(1000));
    const second = gainPlan(state({ selection }), 1, burst.key(1200));
    assert.equal(first.args.delta_db, 0.5);
    assert.equal(first.coalesce, second.coalesce);
    assert.deepEqual(first.combine(first.args, second.args), {
      clip_ids: ["a1", "v1"],
      delta_db: 1,
    });
    assert.equal(gainPlan(state({ selection }), -1, "k").args.delta_db, -0.5);
  });
  test("a pause starts a new burst, so a new undo step", () => {
    const burst = createBurst(600);
    const a = burst.key(1000);
    assert.equal(burst.key(1500), a);
    assert.notEqual(burst.key(3000), a);
  });
  test("needs a selection", () => {
    assert.equal(gainPlan(state(), 1, "k"), null);
  });
});

describe("track mute and solo", () => {
  test("Shift+M toggles the current track's mute", () => {
    assert.deepEqual(trackMutePlan(state()).args, { track_id: "A", mute: true });
    assert.deepEqual(trackMutePlan(state({ focusTrack: "V" })).args, {
      track_id: "V",
      mute: false,
    });
    assert.equal(trackMutePlan(state({ focusTrack: null })), null);
  });
  test("Shift+S solos exclusively; Shift+Alt+S adds to the set", () => {
    assert.deepEqual(soloPlan(state(), true).args, { track_id: "A", exclusive: true });
    assert.deepEqual(soloPlan(state(), false).args, { track_id: "A", exclusive: false });
  });
});

describe("which tracks an edit changed", () => {
  test("compares clips track by track", () => {
    const after = {
      ...project,
      tracks: [
        { ...project.tracks[0], clips: [clip("a1", 0, 2)] },
        project.tracks[1],
        { ...project.tracks[2], clips: [clip("m1", 0, 1)] },
      ],
    };
    assert.deepEqual(changedTracks(project, after), ["A", "M"]);
    assert.deepEqual(changedTracks(project, project), []);
  });
});
