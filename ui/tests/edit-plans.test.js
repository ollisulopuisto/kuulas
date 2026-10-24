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
  moveTrackPlan,
  mutePlan,
  nudgePlan,
  openedRegionClip,
  removeClipsPlan,
  removePlan,
  resetGainsPlan,
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
  rangeMode: "all",
  trackSelection: new Set(),
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
  test("the range from the keyboard is muted in place on all tracks", () => {
    const plan = deletePlan(state(range));
    assert.equal(plan.op, "mute_range");
    assert.deepEqual(plan.args, { start: 2 * S, end: 6 * S, track_ids: ["A", "V", "M"] });
    assert.equal(plan.toast.values.seconds, 4);
  });
  test("selected tracks override: only those, also from the keyboard", () => {
    const plan = deletePlan(
      state({ ...range, rangeMode: "selected", trackSelection: new Set(["V"]) }),
    );
    assert.deepEqual(plan.args.track_ids, ["V"]);
  });
  test("selected-only mode with no track selected refuses instead of doing nothing", () => {
    const plan = deletePlan(state({ ...range, rangeMode: "selected" }));
    assert.deepEqual(plan, { refuse: { key: "ui.scope.none_selected" } });
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
  test("the current track does not narrow a range: it is still all tracks", () => {
    assert.deepEqual(deletePlan(state({ ...range, focusTrack: null })).args.track_ids, [
      "A",
      "V",
      "M",
    ]);
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
  test("selected-only mode with nothing selected refuses", () => {
    assert.ok(liftCutPlan(state({ ...range, rangeMode: "selected" })).refuse);
  });
});

describe("close gap on all tracks", () => {
  test("ripple_delete of the range on the scope's tracks (all by default), no clipboard", () => {
    const plan = closeGapPlan(state(range));
    assert.equal(plan.op, "ripple_delete");
    assert.deepEqual(plan.args, { start: 2 * S, end: 6 * S, track_ids: ["A", "V", "M"] });
    assert.equal(plan.label.key, "ui.edit.label.close_gap");
  });
  test("selected clips: their span", () => {
    const plan = closeGapPlan(state({ selection: new Set(["a2"]) }));
    assert.deepEqual(plan.args, { start: 12 * S, end: 20 * S, track_ids: ["A"] });
  });
  test("nothing selected is null", () => {
    assert.equal(closeGapPlan(state()), null);
  });
});

describe("cut (ripple)", () => {
  test("the range from the keyboard, on all tracks", () => {
    const plan = cutPlan(state(range), { t });
    assert.equal(plan.op, "clipboard_cut");
    assert.deepEqual(plan.args.track_ids, ["A", "V", "M"]);
    assert.equal(plan.args.group_editing, undefined);
    assert.equal(plan.toast.tracks, true);
  });
  test("Shift+X cuts the current track only", () => {
    assert.deepEqual(cutPlan(state(range), { thisTrackOnly: true }).args.track_ids, ["A"]);
  });
  test("selected clips: their span, on their tracks", () => {
    const plan = cutPlan(state({ selection: new Set(["a2", "v1"]) }), { t });
    assert.deepEqual(plan.args, {
      start: 0,
      end: 20 * S,
      track_ids: ["A", "V"],
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

describe("M at the cursor on an implicit portion (owner, 2026-10-24)", () => {
  const silenced = (extra = {}) =>
    clip("a1", 0, 10, {
      auto_silence: [
        [0, 3 * S],
        [5 * S, 8 * S],
      ],
      ...extra,
    });
  const two = (a) => ({
    ...project,
    tracks: [
      { id: "A", clips: [a] },
      { id: "B", clips: [clip("b1", 0, 10)] },
    ],
  });

  test("a clip in a group (both selected): M acts on the cursor's portion, not the group", () => {
    const plan = mutePlan(
      state({ project: two(silenced()), selection: new Set(["a1", "b1"]), playhead: 4 * S }),
    );
    assert.equal(plan.op, "open_gated_region");
    assert.deepEqual(plan.args, { track_id: "A", clip_id: "a1", at: 4 * S, muted: true });
  });

  test("a closed stretch of a grouped clip is opened alone", () => {
    const plan = mutePlan(
      state({ project: two(silenced()), selection: new Set(["a1", "b1"]), playhead: 6 * S }),
    );
    assert.equal(plan.op, "open_gated_region");
    assert.deepEqual(plan.args, { track_id: "A", clip_id: "a1", at: 6 * S });
  });

  test("nothing selected: M acts on the current track's portion under the cursor", () => {
    const plan = mutePlan(state({ project: two(silenced()), playhead: 4 * S }));
    assert.equal(plan.op, "open_gated_region");
    assert.deepEqual(plan.args, { track_id: "A", clip_id: "a1", at: 4 * S, muted: true });
  });

  test("a cursor outside every portion still mutes the selection as before", () => {
    const plan = mutePlan(
      state({ project: two(clip("a1", 0, 10)), selection: new Set(["a1", "b1"]), playhead: 4 * S }),
    );
    assert.equal(plan.op, "set_clips");
  });
});

describe("mute on a closed stretch (BUGS #109)", () => {
  const gated = (gate, clipExtra = {}) => ({
    ...project,
    tracks: [{ id: "A", gate, clips: [clip("a1", 0, 10, clipExtra)] }],
  });
  const closed = [[3 * S, 5 * S]];

  test("M on a clip with the play cursor in a closed stretch opens just that stretch", () => {
    const plan = mutePlan(
      state({ project: gated(closed), selection: new Set(["a1"]), playhead: 4 * S }),
    );
    assert.equal(plan.op, "open_gated_region");
    assert.deepEqual(plan.args, { track_id: "A", clip_id: "a1", at: 4 * S });
    assert.equal(plan.label.key, "ui.edit.label.unmute_region");
  });

  test("M opens only the selected clip's implicit source range after it moved", () => {
    const clipWithSilence = clip("a1", 10, 10, {
      offset: 0,
      auto_silence: [[3 * S, 5 * S]],
    });
    const moved = { ...project, tracks: [{ id: "A", clips: [clipWithSilence] }] };
    const plan = mutePlan(state({ project: moved, selection: new Set(["a1"]), playhead: 14 * S }));
    assert.equal(plan.op, "open_gated_region");
    assert.deepEqual(plan.args, { track_id: "A", clip_id: "a1", at: 14 * S });
    assert.equal(plan.label.key, "ui.edit.label.unmute_region");
  });

  test("M uses the clicked implicit range even if the play cursor is stale", () => {
    const clipWithSilence = clip("a1", 0, 10, { auto_silence: [[3 * S, 5 * S]] });
    const target = { trackId: "A", clipId: "a1", range: [3 * S, 5 * S], implicit: true };
    const plan = mutePlan(
      state({
        project: { ...project, tracks: [{ id: "A", clips: [clipWithSilence] }] },
        selection: new Set(["a1"]),
        playhead: 7 * S,
        implicitRangeTarget: target,
      }),
    );
    assert.equal(plan.op, "open_gated_region");
    assert.deepEqual(plan.args, { track_id: "A", clip_id: "a1", at: 4 * S });
  });

  test("M on a clicked implicit range wins over expanded group selection", () => {
    const clipWithSilence = clip("a1", 0, 10, {
      group: "g1",
      auto_silence: [[3 * S, 5 * S]],
    });
    const plan = mutePlan(
      state({
        project: {
          ...project,
          tracks: [{ id: "A", clips: [clipWithSilence, clip("a2", 12, 8, { group: "g1" })] }],
        },
        selection: new Set(["a1", "a2"]),
        playhead: 7 * S,
        implicitRangeTarget: {
          trackId: "A",
          clipId: "a1",
          range: [3 * S, 5 * S],
          implicit: true,
        },
      }),
    );
    assert.equal(plan.op, "open_gated_region");
    assert.deepEqual(plan.args, { track_id: "A", clip_id: "a1", at: 4 * S });
  });

  test("openedRegionClip finds the clip M opened, so it can be selected for the next M", () => {
    const after = {
      ...project,
      tracks: [
        {
          id: "A",
          clips: [clip("a1", 0, 3), clip("a2", 3, 5, { ungated: true }), clip("a3", 5, 10)],
        },
      ],
    };
    assert.equal(openedRegionClip(after, "A", 4 * S), "a2");
    assert.equal(openedRegionClip(after, "B", 4 * S), null);
  });

  test("openedRegionClip picks the materialized region from the clicked overlapping clip", () => {
    const sourceClip = clip("a1", 0, 10, {
      media: "m1",
      auto_silence: [[3 * S, 5 * S]],
    });
    const after = {
      ...project,
      tracks: [
        {
          id: "A",
          clips: [
            clip("a1", 0, 3, { media: "m1" }),
            clip("a2", 3, 2, { media: "m1", offset: 3 * S }),
            clip("a3", 5, 5, { media: "m1", offset: 5 * S }),
            clip("b1", 0, 10, { media: "m2" }),
          ],
        },
      ],
    };
    assert.equal(openedRegionClip(after, "A", 4 * S, sourceClip), "a2");
  });

  test("the cursor in an implicit opening mutes only that opening", () => {
    const plan = mutePlan(
      state({ project: gated(closed), selection: new Set(["a1"]), playhead: 7 * S }),
    );
    assert.equal(plan.op, "open_gated_region");
    assert.deepEqual(plan.args, { track_id: "A", clip_id: "a1", at: 7 * S, muted: true });
  });

  test("a clip that keeps the mic open or is muted already is toggled whole", () => {
    for (const extra of [{ ungated: true }, { muted: true }]) {
      const plan = mutePlan(
        state({ project: gated(closed, extra), selection: new Set(["a1"]), playhead: 4 * S }),
      );
      assert.equal(plan.op, "set_clips");
    }
  });

  test("more than one clip selected, the cursor in the focused track's closed stretch: just that stretch (owner, 2026-10-24)", () => {
    const two = {
      ...project,
      tracks: [
        { id: "A", gate: closed, clips: [clip("a1", 0, 10)] },
        { id: "B", gate: closed, clips: [clip("b1", 0, 10)] },
      ],
    };
    const plan = mutePlan(
      state({ project: two, selection: new Set(["a1", "b1"]), playhead: 4 * S }),
    );
    assert.equal(plan.op, "open_gated_region");
    assert.equal(plan.args.track_id, "A");
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
  test("by the nudge step, later or earlier (an explicit group goes together on the server)", () => {
    const plan = nudgePlan(state({ selection: new Set(["a1"]) }), 1);
    assert.equal(plan.op, "nudge_clips");
    assert.deepEqual(plan.args, { clip_ids: ["a1"], delta: 480 });
    assert.equal(nudgePlan(state({ selection: new Set(["a1"]) }), -1).args.delta, -480);
  });
  test("needs a selection", () => {
    assert.equal(nudgePlan(state(), 1), null);
  });
});

describe("move to the track above or below (Mod+Up and Mod+Down)", () => {
  test("one track down is direction +1 and up is -1, same time", () => {
    const down = moveTrackPlan(state({ selection: new Set(["a1"]) }), 1);
    assert.equal(down.op, "move_clips_to_track");
    assert.deepEqual(down.args, { clip_ids: ["a1"], direction: 1, delta: 0 });
    const up = moveTrackPlan(state({ selection: new Set(["v1"]) }), -1);
    assert.equal(up.args.direction, -1);
  });
  test("a selection that is already on the first or last track cannot move that way", () => {
    assert.equal(moveTrackPlan(state({ selection: new Set(["a1"]) }), -1), null);
    assert.equal(moveTrackPlan(state({ selection: new Set(["a1", "v1"]) }), -1), null);
    assert.ok(moveTrackPlan(state({ selection: new Set(["a1", "v1"]) }), 1));
  });
  test("needs a selection and a project", () => {
    assert.equal(moveTrackPlan(state(), 1), null);
    assert.equal(moveTrackPlan({ ...state(), project: null }, 1), null);
  });
  test("a silent step: no toast", () => {
    assert.equal(moveTrackPlan(state({ selection: new Set(["a1"]) }), 1).toast, null);
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
  test("this track only names the current track", () => {
    assert.deepEqual(removePlan(state(range), { thisTrackOnly: true }).args.track_ids, ["A"]);
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

describe("reset gains to 0 dB", () => {
  const withGains = (tracks, buses) =>
    state({
      project: {
        ...project,
        tracks: project.tracks.map((track, i) => ({ ...track, gain_db: tracks[i] ?? 0 })),
        buses: buses.map((gain_db, i) => ({ id: `b${i}`, gain_db })),
      },
    });

  test("one reset_gains edit; the toast counts the tracks and buses that are not at 0", () => {
    const plan = resetGainsPlan(withGains([-3, 0, 1.5], [2, 0]));
    assert.equal(plan.op, "reset_gains");
    assert.deepEqual(plan.args, {});
    assert.equal(plan.toast.key, "ui.edit.toast.reset_gains");
    assert.equal(plan.toast.values.count, 3);
    assert.equal(plan.label.key, "ui.edit.label.reset_gains");
  });
  test("a bus alone is enough", () => {
    assert.equal(resetGainsPlan(withGains([0, 0, 0], [-1])).toast.values.count, 1);
  });
  test("with every gain at 0, or no project, it does not apply (the menu dims it)", () => {
    assert.equal(resetGainsPlan(withGains([0, 0, 0], [0])), null);
    assert.equal(resetGainsPlan(state()), null);
    assert.equal(resetGainsPlan(null), null);
  });
});

test("M on an audible implicit opening mutes that portion, including legacy gates", () => {
  for (const legacy of [false, true]) {
    const ranges = [
      [0, 3 * S],
      [5 * S, 10 * S],
    ];
    const c = clip("a1", 0, 10, {
      offset: 0,
      media: "m",
      ...(legacy ? {} : { auto_silence: ranges }),
    });
    const project = { tracks: [{ id: "A", gate: legacy ? ranges : [], clips: [c] }] };
    const change = mutePlan(state({ project, selection: new Set(["a1"]), playhead: 4 * S }));
    assert.equal(change.op, "open_gated_region");
    assert.deepEqual(change.args, { track_id: "A", clip_id: "a1", at: 4 * S, muted: true });
    const after = {
      tracks: [
        {
          id: "A",
          clips: [
            { ...c, length: 3 * S },
            {
              ...c,
              id: "portion",
              start: 3 * S,
              offset: 3 * S,
              length: 2 * S,
              muted: true,
              ungated: true,
              auto_silence: [],
            },
            { ...c, start: 5 * S, offset: 5 * S, length: 5 * S },
          ],
        },
      ],
    };
    assert.equal(openedRegionClip(after, "A", 4 * S, c, legacy ? ranges : []), "portion");
  }
});
