import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  expandGroups,
  groupClipsPlan,
  mergeClipsPlan,
  mergeSummary,
  toggleGroupSelection,
  ungroupClipsPlan,
} from "../clip-groups.js";
import { createRegistry } from "../commands.js";
import { registerEditCommands } from "../edit-commands.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";

const clip = (id, start, length, extra = {}) => ({
  id,
  media: "m1",
  start,
  offset: start,
  length,
  gain_db: 0,
  pan: 0,
  muted: false,
  envelope: [],
  xfade_in: 0,
  xfade_out: 0,
  ...extra,
});

const project = {
  rate: 48000,
  tracks: [
    {
      id: "A",
      clips: [
        clip("a1", 0, 100, { group: "g1" }),
        clip("a2", 100, 100),
        clip("a3", 500, 100, { group: "g2" }),
      ],
    },
    { id: "B", clips: [clip("b1", 0, 100, { group: "g1" }), clip("b2", 0, 50, { group: "g2" })] },
  ],
};
const state = (ids, extra = {}) => ({ project, selection: new Set(ids), ...extra });

describe("a group is one thing for selection", () => {
  test("selecting one member selects them all, on every track", () => {
    assert.deepEqual([...expandGroups(project, new Set(["a1"]))].sort(), ["a1", "b1"]);
  });

  test("ungrouped clips stay alone and other ids are kept", () => {
    assert.deepEqual([...expandGroups(project, new Set(["a2"]))], ["a2"]);
    assert.deepEqual([...expandGroups(project, new Set())], []);
  });

  test("a project without groups is returned as the same ids", () => {
    const plain = { tracks: [{ id: "A", clips: [clip("x", 0, 1)] }] };
    assert.deepEqual([...expandGroups(plain, new Set(["x"]))], ["x"]);
    assert.deepEqual([...expandGroups(null, new Set(["x"]))], ["x"]);
  });

  test("toggling a member adds or removes the whole group", () => {
    const added = toggleGroupSelection(project, new Set(["a2"]), "b1");
    assert.deepEqual([...added].sort(), ["a1", "a2", "b1"]);
    const removed = toggleGroupSelection(project, added, "a1");
    assert.deepEqual([...removed], ["a2"]);
  });

  test("toggling an ungrouped clip works as before", () => {
    assert.deepEqual([...toggleGroupSelection(project, new Set(), "a2")], ["a2"]);
    assert.deepEqual([...toggleGroupSelection(project, new Set(["a2"]), "a2")], []);
  });
});

describe("what merge would do", () => {
  const touching = {
    tracks: [
      {
        id: "A",
        clips: [clip("p", 0, 100), clip("q", 100, 100), clip("r", 200, 100), clip("s", 400, 50)],
      },
    ],
  };

  test("counts clips merged, clips left after, and clips that could not join", () => {
    assert.deepEqual(mergeSummary(touching, new Set(["p", "q", "r", "s"])), {
      merged: 3,
      into: 1,
      left: 1,
    });
  });

  test("two runs are two results", () => {
    const two = {
      tracks: [
        {
          id: "A",
          clips: [clip("p", 0, 10), clip("q", 10, 10), clip("r", 50, 10), clip("s", 60, 10)],
        },
      ],
    };
    assert.deepEqual(mergeSummary(two, new Set(["p", "q", "r", "s"])), {
      merged: 4,
      into: 2,
      left: 0,
    });
  });

  test("a different gain, source or group, or an envelope, stops a join", () => {
    for (const other of [
      { gain_db: -3 },
      { media: "m2" },
      { group: "g9" },
      { envelope: [[5, 0]] },
      { xfade_in: 4 },
      { muted: true },
      { offset: 999 },
    ]) {
      const p = { tracks: [{ id: "A", clips: [clip("p", 0, 100), clip("q", 100, 100, other)] }] };
      assert.equal(mergeSummary(p, new Set(["p", "q"])).merged, 0, JSON.stringify(other));
    }
  });

  test("clips that are not selected do not join", () => {
    assert.equal(mergeSummary(touching, new Set(["p", "r"])).merged, 0);
  });
});

describe("the plans", () => {
  test("group needs two clips and not already one group", () => {
    assert.equal(groupClipsPlan(state([])), null);
    assert.equal(groupClipsPlan(state(["a2"])), null);
    assert.equal(groupClipsPlan(state(["a1", "b1"])), null); // already one group
    const plan = groupClipsPlan(state(["a2", "a3"]));
    assert.equal(plan.op, "group_clips");
    assert.deepEqual(plan.args, { clip_ids: ["a2", "a3"] });
    assert.equal(plan.label.key, "ui.edit.label.group_clips");
  });

  test("ungroup needs a grouped clip in the selection", () => {
    assert.equal(ungroupClipsPlan(state(["a2"])), null);
    assert.equal(ungroupClipsPlan(state([])), null);
    const plan = ungroupClipsPlan(state(["a1", "a2"]));
    assert.equal(plan.op, "ungroup_clips");
    assert.deepEqual(plan.args, { clip_ids: ["a1", "a2"] });
  });

  test("merge needs clips that can join, and says what it will do", () => {
    const p = {
      rate: 48000,
      tracks: [{ id: "A", clips: [clip("p", 0, 10), clip("q", 10, 10), clip("z", 90, 10)] }],
    };
    assert.equal(mergeClipsPlan({ project: p, selection: new Set(["p", "z"]) }), null);
    const plan = mergeClipsPlan({ project: p, selection: new Set(["p", "q", "z"]) });
    assert.equal(plan.op, "merge_clips");
    assert.deepEqual(plan.args, { clip_ids: ["p", "q", "z"] });
    assert.equal(plan.toast.key, "ui.edit.toast.merge_partial");
    assert.deepEqual(plan.toast.values, { count: 2, into: 1, left: 1 });
    const all = mergeClipsPlan({ project: p, selection: new Set(["p", "q"]) });
    assert.equal(all.toast.key, "ui.edit.toast.merge");
  });
});

describe("the commands", () => {
  function setup(s) {
    const registry = createRegistry();
    const sent = [];
    registerEditCommands(registry, {
      t: (key, values = {}) => `${key}${JSON.stringify(values)}`,
      formatSeconds: String,
      app: {
        getState: () => s,
        patch: () => {},
        edit: (change) => sent.push(change),
        toast: () => {},
        now: () => 0,
        copy: () => Promise.resolve(true),
        focusName: () => {},
        refreshClipboard: () => {},
      },
    });
    return { registry, sent };
  }

  test("they are in the keymap, registered, and enabled only when they can act", () => {
    const ids = new Set(DEFAULT_KEYMAP.map((e) => e.id));
    for (const id of ["edit.group", "edit.ungroup", "edit.merge"]) assert.ok(ids.has(id), id);
    const { registry } = setup(state([]));
    for (const id of ["edit.group", "edit.ungroup", "edit.merge"]) {
      assert.equal(registry.status(id), "ready", id);
      assert.equal(registry.can(id, state([])), false, id);
    }
    assert.equal(registry.can("edit.group", state(["a2", "a3"])), true);
    assert.equal(registry.can("edit.ungroup", state(["a1"])), true);
    assert.equal(registry.can("edit.merge", state(["a1", "a2"])), false);
  });

  test("running one sends its op with a label", () => {
    const s = state(["a2", "a3"]);
    const { registry, sent } = setup(s);
    registry.run("edit.group");
    assert.equal(sent.length, 1);
    assert.equal(sent[0].op, "group_clips");
    assert.match(sent[0].label, /^ui\.edit\.label\.group_clips/);
  });
});
