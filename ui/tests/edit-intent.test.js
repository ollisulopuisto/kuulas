import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  closeGapPlan,
  copyPlan,
  cutPlan,
  deletePlan,
  liftCutPlan,
  removePlan,
} from "../edit-plans.js";
import { editRange, editTarget, intentPatch } from "../intent.js";
import { activeLoop, rangeAvailable } from "../loop-range.js";
import { dimmedTracks, scopeChip } from "../range-scope.js";
import { playSelectionRequest } from "../rehearse.js";
import { getState, initialState, resetState, serverPatch, setState } from "../store.js";

const S = 48000;
const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;
const clip = (id, start, seconds) => ({
  id,
  start: start * S,
  length: seconds * S,
  muted: false,
});
const project = {
  rate: S,
  tracks: [
    { id: "A", name: "Olli", clips: [clip("a1", 0, 10), clip("a2", 12, 8)] },
    { id: "V", name: "Kari", clips: [clip("v1", 0, 10)] },
    { id: "M", name: "Music", clips: [] },
  ],
};
const base = (extra = {}) => ({
  project,
  selection: new Set(),
  focusTrack: "A",
  focusBus: null,
  playhead: 4 * S,
  inPoint: null,
  outPoint: null,
  rangeMode: "all",
  trackSelection: new Set(),
  rangeTracks: new Set(),
  ...extra,
});
const marks = { inPoint: 2 * S, outPoint: 6 * S };
const picked = new Set(["a2", "v1"]);

describe("which of the range and the clips the next edit touches", () => {
  test("marks then clips: the clips win and the marks stay", () => {
    const state = base({ ...marks, selection: picked, intent: "clips" });
    assert.equal(editTarget(state), "clips");
    assert.equal(editRange(state), null);
    assert.equal(state.inPoint, 2 * S);
  });

  test("clips then marks: the range wins", () => {
    const state = base({ ...marks, selection: picked, intent: "range" });
    assert.equal(editTarget(state), "range");
    assert.deepEqual(editRange(state), { start: 2 * S, end: 6 * S });
  });

  test("no intent yet is the old behaviour: the range wins", () => {
    assert.equal(editTarget(base({ ...marks, selection: picked })), "range");
  });

  test("a lone target is the target whatever was touched last", () => {
    assert.equal(editTarget(base({ ...marks, intent: "clips" })), "range");
    assert.equal(editTarget(base({ selection: picked, intent: "range" })), "clips");
    assert.equal(editTarget(base()), null);
  });

  test("a mark on its own is no range", () => {
    assert.equal(editTarget(base({ inPoint: S, selection: picked, intent: "range" })), "clips");
  });
});

describe("the plans follow the intent", () => {
  const clipsFirst = base({ ...marks, selection: picked, intent: "clips" });
  const rangeFirst = base({ ...marks, selection: picked, intent: "range" });

  test("Backspace: mutes the selected clips, or the range", () => {
    const onClips = deletePlan(clipsFirst);
    assert.equal(onClips.op, "set_clips");
    assert.deepEqual(onClips.args, { clip_ids: ["a2", "v1"], muted: true });
    const onRange = deletePlan(rangeFirst);
    assert.equal(onRange.op, "mute_range");
    assert.deepEqual(onRange.args, {
      start: 2 * S,
      end: 6 * S,
      track_ids: ["A", "V", "M"],
    });
  });

  test("X, Alt+X, Cmd+X and close gap use the selected clips' span", () => {
    for (const plan of [
      removePlan(clipsFirst),
      closeGapPlan(clipsFirst),
      liftCutPlan(clipsFirst, { t }),
      cutPlan(clipsFirst, { t }),
    ]) {
      assert.equal(plan.args.start, 0);
      assert.equal(plan.args.end, 20 * S);
      assert.deepEqual(plan.args.track_ids, ["A", "V"]);
    }
  });

  test("X and the others use the range when the marks came last", () => {
    for (const plan of [removePlan(rangeFirst), closeGapPlan(rangeFirst)]) {
      assert.equal(plan.args.start, 2 * S);
      assert.equal(plan.args.end, 6 * S);
      assert.deepEqual(plan.args.track_ids, ["A", "V", "M"]);
    }
  });

  test("copy sends the clip ids, or the range", () => {
    assert.deepEqual(copyPlan(clipsFirst, t).body.clip_ids, ["a2", "v1"]);
    const onRange = copyPlan(rangeFirst, t).body;
    assert.equal(onRange.start, 2 * S);
    assert.equal(onRange.clip_ids, undefined);
  });

  test("selected-only mode with no track selected refuses a range, not the clips", () => {
    const strict = { rangeMode: "selected" };
    assert.equal(deletePlan({ ...clipsFirst, ...strict }).op, "set_clips");
    assert.ok(deletePlan({ ...rangeFirst, ...strict }).refuse);
  });

  test("clearing the selection leaves the range as the target, clearing the marks the clips", () => {
    assert.equal(deletePlan({ ...clipsFirst, selection: new Set() }).op, "mute_range");
    const noMarks = { ...clipsFirst, inPoint: null, outPoint: null };
    assert.equal(deletePlan(noMarks).op, "set_clips");
  });

  test("a muted selection with marks and clips-intent does nothing rather than mute the range", () => {
    const muted = {
      ...clipsFirst,
      project: {
        ...project,
        tracks: project.tracks.map((tr) => ({
          ...tr,
          clips: tr.clips.map((c) => ({ ...c, muted: true })),
        })),
      },
    };
    assert.equal(deletePlan(muted), null);
  });
});

describe("what sets the intent (intentPatch)", () => {
  const prev = base({ ...marks, selection: new Set(["a1"]), intent: "range" });

  test("a new selection after the marks makes the clips the intent", () => {
    assert.deepEqual(intentPatch(prev, { selection: new Set(["a2"]) }), { intent: "clips" });
    assert.deepEqual(intentPatch(prev, { selection: new Set(["a1", "a2"]) }), {
      intent: "clips",
    });
  });

  test("new marks, a dragged range or painted lanes make the range the intent", () => {
    const clipsLast = { ...prev, intent: "clips" };
    assert.deepEqual(intentPatch(clipsLast, { inPoint: S }), { intent: "range" });
    assert.deepEqual(intentPatch(clipsLast, { outPoint: 9 * S }), { intent: "range" });
    assert.deepEqual(intentPatch(clipsLast, { rangeTracks: new Set(["A"]) }), {
      intent: "range",
    });
  });

  test("selecting and marking in one patch (a dragged range) is the range", () => {
    assert.deepEqual(
      intentPatch(
        { ...prev, intent: "clips" },
        { selection: new Set(["a2"]), inPoint: 0, outPoint: 3 * S },
      ).intent,
      "range",
    );
  });

  test("clearing, unchanged values and unrelated patches change nothing", () => {
    assert.equal(intentPatch(prev, { selection: new Set() }), null);
    assert.equal(intentPatch(prev, { inPoint: null, outPoint: null }), null);
    assert.equal(intentPatch(prev, { selection: new Set(["a1"]) }), null);
    assert.equal(intentPatch(prev, { inPoint: 2 * S }), null);
    assert.equal(intentPatch(prev, { rangeTracks: new Set() }), null);
    assert.equal(intentPatch(prev, { playhead: 5 }), null);
  });

  test("an explicit intent in the patch is kept", () => {
    assert.equal(intentPatch(prev, { selection: new Set(["a2"]), intent: "range" }), null);
  });
});

describe("the store applies it, and undo or redo leave it alone", () => {
  test("marks, then clips, then marks again", () => {
    resetState();
    setState({ project, inPoint: 2 * S, outPoint: 6 * S });
    assert.equal(getState().intent, "range");
    setState({ selection: new Set(["a1"]) });
    assert.equal(getState().intent, "clips");
    assert.equal(editTarget(getState()), "clips");
    setState({ outPoint: 8 * S });
    assert.equal(getState().intent, "range");
    resetState();
  });

  test("a server answer that trims the selection (after undo) does not change it", () => {
    resetState();
    setState({ project, inPoint: 2 * S, outPoint: 6 * S, selection: new Set(["a1", "a2"]) });
    assert.equal(getState().intent, "range"); // tie: the range, as before
    setState({ selection: new Set(["a1", "a2"]) });
    setState({ selection: new Set(["a1"]) });
    assert.equal(getState().intent, "clips");
    const undone = {
      project: { tracks: project.tracks.map((tr) => ({ ...tr, clips: [] })) },
      head: "h2",
    };
    const patch = serverPatch(undone, getState());
    assert.equal(patch.selection.size, 0);
    setState(patch);
    assert.equal(getState().intent, "clips");
    resetState();
  });

  test("a server answer that trims one clip of several keeps the intent", () => {
    resetState();
    setState({ project, inPoint: 2 * S, outPoint: 6 * S });
    setState({ selection: new Set(["a1", "a2"]) });
    const answer = { project: { tracks: [{ ...project.tracks[0], clips: [clip("a1", 0, 10)] }] } };
    const patch = serverPatch(answer, getState());
    assert.equal(patch.selection.size, 1);
    setState(patch);
    assert.equal(getState().intent, "clips");
    resetState();
  });

  test("the intent is UI state: it starts at the range", () => {
    assert.equal(initialState().intent, "range");
  });
});

describe("the chip and the dimming", () => {
  test("marks and clips, clips last: the chip names the clips", () => {
    const state = base({ ...marks, selection: picked, intent: "clips" });
    assert.deepEqual(scopeChip(state), { kind: "clips", count: 2 });
    assert.equal(dimmedTracks({ ...state, rangeMode: "selected" }).size, 0);
  });

  test("range last: the chip is the range chip, as before", () => {
    const state = base({ ...marks, selection: picked, intent: "range" });
    assert.deepEqual(scopeChip(state), {
      kind: "range",
      start: 2 * S,
      end: 6 * S,
      all: true,
      count: 3,
      names: [],
    });
  });

  test("clips without any marks: no chip, as before", () => {
    assert.equal(scopeChip(base({ selection: picked, intent: "clips" })), null);
  });

  test("clips last in selected-only mode with no track: the clips chip, not the warning", () => {
    const state = base({
      ...marks,
      selection: picked,
      intent: "clips",
      rangeMode: "selected",
    });
    assert.deepEqual(scopeChip(state), { kind: "clips", count: 2 });
  });
});

describe("commands that are not edits keep marks first", () => {
  test("loop playback uses the marks even when clips were selected later", () => {
    const state = base({ ...marks, selection: picked, intent: "clips", loop: true });
    const range = rangeAvailable(state);
    assert.equal(range.source, "marks");
    assert.deepEqual(activeLoop(state), [2 * S, 6 * S]);
  });

  test("play selection plays the marks", () => {
    const state = base({ ...marks, selection: picked, intent: "clips" });
    assert.deepEqual(playSelectionRequest(state), { at: 2 * S, until: 6 * S, skip: null });
  });
});
