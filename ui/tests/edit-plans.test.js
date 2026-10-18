import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  addTrackPlan,
  changedTracks,
  closeGapPlan,
  createBurst,
  cutPlan,
  deleteEmptyTracksPlan,
  deletePlan,
  fadePlan,
  gainPlan,
  liftCutPlan,
  mutePlan,
  nudgePlan,
  removeClipsPlan,
  removePlan,
  soloPlan,
  splitPlan,
  trackMutePlan,
  trimPlan,
} from "../edit-plans.js";

const S = 48000;
const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;
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

describe("lift-cut (copy, then soft delete)", () => {
  test("the same target as X, but a clipboard_lift_cut with a clear label", () => {
    const lift = liftCutPlan(state(range));
    const cut = cutPlan(state(range));
    assert.equal(lift.op, "clipboard_lift_cut");
    assert.deepEqual(lift.args, cut.args);
    assert.equal(lift.label.key, "ui.edit.label.lift_cut");
    assert.equal(lift.toast.tracks, true);
  });
  test("selected clips: their span, like X", () => {
    const sel = state({ selection: new Set(["a2", "v1"]) });
    assert.deepEqual(liftCutPlan(sel).args, cutPlan(sel).args);
  });
  test("nothing to act on is null", () => {
    assert.equal(liftCutPlan(state({ focusTrack: null })), null);
  });
});

describe("close gap on all tracks", () => {
  test("ripple_delete of the range on every track, no clipboard", () => {
    const plan = closeGapPlan(state(range));
    assert.equal(plan.op, "ripple_delete");
    assert.deepEqual(plan.args, { start: 2 * S, end: 6 * S });
    assert.equal(plan.label.key, "ui.edit.label.close_gap");
  });
  test("selected clips: their span", () => {
    const plan = closeGapPlan(state({ selection: new Set(["a2"]) }));
    assert.deepEqual(plan.args, { start: 12 * S, end: 20 * S });
  });
  test("nothing selected is null", () => {
    assert.equal(closeGapPlan(state()), null);
  });
});

describe("cut (ripple)", () => {
  test("the range, on the current track plus the group when group editing is on", () => {
    const plan = cutPlan(state(range), { t });
    assert.equal(plan.op, "clipboard_cut");
    assert.deepEqual(plan.args, {
      start: 2 * S,
      end: 6 * S,
      track_ids: ["A"],
      group_editing: true,
      name: 'ui.clipboard.auto_name{"count":1,"name":"ui.clipboard.untitled_track{}","at":"00:00:02"}',
    });
    assert.equal(plan.toast.tracks, true);
  });
  test("Shift+X never takes the group along", () => {
    assert.equal(cutPlan(state(range), { thisTrackOnly: true }).args.group_editing, false);
  });
  test("selected clips: their span, on their tracks", () => {
    const plan = cutPlan(state({ selection: new Set(["a2", "v1"]) }), { t });
    assert.deepEqual(plan.args, {
      start: 0,
      end: 20 * S,
      track_ids: ["A", "V"],
      group_editing: true,
      name: 'ui.clipboard.auto_name{"count":2,"name":"ui.clipboard.untitled_track{}","at":"00:00:00"}',
    });
  });
  test("a range set to all tracks (Select > Range on all tracks) cuts on every track", () => {
    const plan = cutPlan(state({ ...range, rangeTracks: ["A", "V", "M"] }));
    assert.deepEqual(plan.args.track_ids, ["A", "V", "M"]);
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

describe("fade", () => {
  test("G fades the current track's clip under the play cursor", () => {
    const plan = fadePlan(state({ playhead: 1 * S }));
    assert.equal(plan.op, "set_fade_at");
    assert.deepEqual(plan.args, { clip_id: "a1", frame: 1 * S });
  });

  test("the first frame of a clip counts as under the cursor, its end does not", () => {
    assert.equal(fadePlan(state({ playhead: 12 * S }))?.args.clip_id, "a2");
    assert.equal(fadePlan(state({ playhead: 10 * S })), null);
  });

  test("a selected clip holding the cursor wins over the current track", () => {
    const plan = fadePlan(state({ selection: new Set(["v1"]), playhead: 4 * S }));
    assert.equal(plan.args.clip_id, "v1");
  });

  test("a selected clip that does not hold the cursor is skipped for the track's", () => {
    const plan = fadePlan(state({ selection: new Set(["a2"]), playhead: 4 * S }));
    assert.equal(plan.args.clip_id, "a1");
  });

  test("nothing under the cursor, no current track or no project: no plan", () => {
    assert.equal(fadePlan(state({ playhead: 11 * S })), null);
    assert.equal(fadePlan(state({ focusTrack: null })), null);
    assert.equal(fadePlan({ project: null }), null);
  });
});

describe("remove (X): ripple delete that never touches the clipboard", () => {
  test("the same target as Cut, but a plain cut_range edit", () => {
    const remove = removePlan(state(range));
    const cut = cutPlan(state(range));
    assert.equal(remove.op, "cut_range");
    const { name: _name, ...sameArgs } = cut.args;
    assert.deepEqual(remove.args, sameArgs);
    assert.equal(remove.label.key, "ui.edit.label.remove");
    assert.equal(remove.toast.key, "ui.edit.toast.remove");
    assert.equal(remove.toast.tracks, true);
  });
  test("this track only turns group editing off", () => {
    assert.equal(removePlan(state(range), { thisTrackOnly: true }).args.group_editing, false);
  });
  test("selected clips: their span; nothing to act on is null", () => {
    const sel = state({ selection: new Set(["a2", "v1"]) });
    assert.deepEqual(removePlan(sel).args.track_ids, cutPlan(sel).args.track_ids);
    assert.equal(removePlan(state({ focusTrack: null })), null);
  });
});

describe("remove clips (Cmd+Backspace): really delete the selected clips, nothing else moves", () => {
  test("a delete_clips edit for the selected clips, muted ones too", () => {
    const sel = state({ selection: new Set(["a2", "v1"]) });
    const plan = removeClipsPlan(sel);
    assert.equal(plan.op, "delete_clips");
    assert.deepEqual([...plan.args.clip_ids].sort(), ["a2", "v1"]);
    assert.equal(plan.label.key, "ui.edit.label.remove_clips");
    assert.equal(plan.toast.key, "ui.edit.toast.remove_clips");
    assert.equal(plan.toast.values.count, 2);
  });
  test("it ignores the marked range: it acts on selected clips only", () => {
    const plan = removeClipsPlan(state({ ...range, selection: new Set(["a1"]) }));
    assert.deepEqual(plan.args.clip_ids, ["a1"]);
  });
  test("nothing selected is null", () => {
    assert.equal(removeClipsPlan(state({ selection: new Set() })), null);
    assert.equal(removeClipsPlan(null), null);
  });
});

describe("add a track (empty, ready for a music bed or a voice)", () => {
  const t = (key, values = {}) => `${key}${values.n ?? ""}`;
  test("a speech track and a music track: add_track with a name and the kind", () => {
    const speech = addTrackPlan(state(), "speech", { t });
    assert.equal(speech.op, "add_track");
    assert.equal(speech.args.kind, "speech");
    assert.match(speech.args.name, /^ui\.track\.new_speech/);
    const music = addTrackPlan(state(), "music", { t });
    assert.equal(music.args.kind, "music");
    assert.match(music.args.name, /^ui\.track\.new_music/);
    assert.equal(music.label.key, "ui.edit.label.add_track");
    assert.equal(music.toast.key, "ui.edit.toast.add_track");
  });
  test("the number goes on past the tracks that exist", () => {
    const plan = addTrackPlan(state(), "speech", { t });
    const count = state().project.tracks.length;
    assert.equal(plan.args.name, `ui.track.new_speech${count + 1}`);
  });
  test("no project, nothing", () => {
    assert.equal(addTrackPlan(null, "music", { t }), null);
  });
});

describe("delete the empty tracks", () => {
  test("a delete_empty_tracks edit, only when some track holds no clip", () => {
    const withEmpty = state({
      project: {
        ...state().project,
        tracks: [...state().project.tracks, { id: "E", name: "Music 4", clips: [] }],
      },
    });
    const plan = deleteEmptyTracksPlan(withEmpty);
    assert.equal(plan.op, "delete_empty_tracks");
    const empties = withEmpty.project.tracks.filter((track) => track.clips.length === 0);
    assert.equal(plan.toast.values.count, empties.length);
    assert.ok(empties.some((track) => track.id === "E"));
    assert.equal(plan.label.key, "ui.edit.label.delete_empty_tracks");
  });
  test("with no empty track, or no project, it does not apply", () => {
    const full = state({
      project: {
        ...state().project,
        tracks: state().project.tracks.map((t) => ({
          ...t,
          clips: t.clips.length ? t.clips : [{ id: "x", start: 0, length: 1 }],
        })),
      },
    });
    assert.equal(deleteEmptyTracksPlan(full), null);
    assert.equal(deleteEmptyTracksPlan(null), null);
  });
});
