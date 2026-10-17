import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { registerEditCommands } from "../edit-commands.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";

const S = 48000;
const clip = (id, start, seconds) => ({ id, start: start * S, length: seconds * S, muted: false });
const project = {
  rate: S,
  tracks: [
    { id: "A", mute: false, clips: [clip("a1", 0, 10)] },
    { id: "V", mute: false, clips: [clip("v1", 0, 10)] },
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
  groupEditing: true,
  ...extra,
});

function setup(state) {
  const registry = createRegistry();
  const sent = [];
  const patches = [];
  const toasts = [];
  let now = 1000;
  registerEditCommands(registry, {
    t: (key, values = {}) => `${key}${JSON.stringify(values)}`,
    formatSeconds: (value) => String(value),
    app: {
      getState: () => state,
      patch: (p) => patches.push(p),
      edit: (change) => sent.push(change),
      toast: (text, options) => toasts.push([text, options]),
      now: () => now,
    },
  });
  return {
    registry,
    sent,
    patches,
    toasts,
    advance: (ms) => {
      now += ms;
    },
  };
}

const WORKING = [
  "edit.split",
  "edit.split_all",
  "edit.delete",
  "edit.cut",
  "edit.cut_track",
  "clip.mute",
  "track.mute",
  "track.solo",
  "track.solo_add",
  "group.toggle",
  "edit.trim_start",
  "edit.trim_end",
  "edit.nudge_left",
  "edit.nudge_right",
  "edit.select_all_track",
  "edit.select_all",
  "clip.gain_up",
  "clip.gain_down",
];

describe("the editing commands", () => {
  test("every one is in the keymap data and is ready", () => {
    const ids = new Set(DEFAULT_KEYMAP.map((e) => e.id));
    const { registry } = setup(base());
    for (const id of WORKING) {
      assert.ok(ids.has(id), `${id} has a keymap entry`);
      assert.equal(registry.status(id), "ready", id);
    }
  });

  test("the clipboard, lift-cut, compare, close-gap-all and fade stay planned", () => {
    const { registry } = setup(base());
    for (const id of ["edit.copy", "edit.paste", "clip.fade"]) {
      assert.notEqual(registry.status(id), "ready", id);
    }
  });

  test("each is disabled when there is nothing to act on", () => {
    const { registry } = setup(base());
    const empty = base({ focusTrack: null });
    for (const id of [
      "edit.delete",
      "edit.cut",
      "edit.cut_track",
      "clip.mute",
      "edit.nudge_left",
      "clip.gain_up",
      "edit.split",
      "edit.trim_start",
      "track.mute",
      "edit.select_all_track",
    ]) {
      assert.equal(registry.can(id, empty), false, id);
    }
    assert.equal(registry.can("edit.select_all", empty), true);
    assert.equal(registry.can("group.toggle", empty), true);
    assert.equal(registry.can("group.toggle", { project: null }), false);
  });

  test("split sends split_clips with a translated label and a toast with Undo after the answer", () => {
    const h = setup(base());
    assert.equal(h.registry.run("edit.split", null, base()), true);
    assert.equal(h.sent.length, 1);
    assert.equal(h.sent[0].op, "split_clips");
    assert.match(h.sent[0].label, /^ui\.edit\.label\.split/);
    h.sent[0].done({ project });
    assert.equal(h.toasts.length, 1);
    assert.match(h.toasts[0][0], /^ui\.edit\.toast\.split/);
    assert.deepEqual(h.toasts[0][1], { undo: true });
  });

  test("a cut toast counts the tracks the answer shows as changed", () => {
    const state = base({ inPoint: 2 * S, outPoint: 6 * S });
    const h = setup(state);
    h.registry.run("edit.cut", null, state);
    const after = {
      ...project,
      tracks: project.tracks.map((t) => ({ ...t, clips: [clip(t.id, 0, 6)] })),
    };
    h.sent[0].done({ project: after });
    assert.match(h.toasts[0][0], /"count":2/);
    assert.match(h.toasts[0][0], /"seconds":"4"/);
  });

  test("an edit that changed nothing says so instead of 'on 0 tracks'", () => {
    const state = base({ inPoint: 2 * S, outPoint: 6 * S });
    const h = setup(state);
    h.registry.run("edit.delete", null, state);
    h.sent[0].done({ project });
    assert.match(h.toasts[0][0], /^ui\.edit\.toast\.nothing/);
  });

  test("nudge and gain are silent", () => {
    const state = base({ selection: new Set(["a1"]) });
    const h = setup(state);
    h.registry.run("edit.nudge_right", null, state);
    h.registry.run("clip.gain_up", null, state);
    h.sent[0].done?.({ project });
    h.sent[1].done?.({ project });
    assert.equal(h.toasts.length, 0);
  });

  test("gain presses close together share a coalesce key and a pause starts a new one", () => {
    const state = base({ selection: new Set(["a1"]) });
    const h = setup(state);
    h.registry.run("clip.gain_up", null, state);
    h.advance(100);
    h.registry.run("clip.gain_up", null, state);
    h.advance(2000);
    h.registry.run("clip.gain_down", null, state);
    assert.equal(h.sent[0].coalesce, h.sent[1].coalesce);
    assert.notEqual(h.sent[1].coalesce, h.sent[2].coalesce);
    assert.equal(typeof h.sent[0].combine, "function");
  });

  test("select all picks the clip ids; E flips group editing", () => {
    const state = base();
    const h = setup(state);
    h.registry.run("edit.select_all", null, state);
    assert.deepEqual([...h.patches[0].selection], ["a1", "v1"]);
    h.registry.run("group.toggle", null, state);
    assert.deepEqual(h.patches[1], { groupEditing: false });
  });

  test("a command that cannot apply does not send anything", () => {
    const state = base({ focusTrack: null });
    const h = setup(state);
    assert.equal(h.registry.run("edit.cut", null, state), false);
    assert.equal(h.sent.length, 0);
  });
});
