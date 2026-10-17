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
  const copied = [];
  let refreshed = 0;
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
      copy: (body) => {
        copied.push(body);
        return Promise.resolve(true);
      },
      refreshClipboard: () => {
        refreshed += 1;
      },
    },
  });
  return {
    registry,
    copied,
    refreshed: () => refreshed,
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
  "edit.copy",
  "edit.paste",
  "edit.paste_overwrite",
  "edit.paste_track",
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

  test("lift-cut, compare, close-gap-all and fade stay planned; no key is bound to lift-cut", () => {
    const { registry } = setup(base());
    const keys = DEFAULT_KEYMAP.flatMap((e) => [e.keys.mac, e.keys.other].flat());
    assert.equal(keys.includes("Alt+X"), false);
    for (const id of ["clip.fade"]) {
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

describe("the clipboard commands (WP46)", () => {
  const entry = { id: "e1", name: "", length: 5 * S, clips: 1, slots: 1, missing_here: 0 };
  const withClip = (extra = {}) => base({ clipboard: [entry], ...extra });

  test("copy needs a selection or a range; paste needs a non-empty clipboard", () => {
    const { registry } = setup(base());
    assert.equal(registry.can("edit.copy", base()), false);
    assert.equal(registry.can("edit.copy", base({ selection: new Set(["a1"]) })), true);
    assert.equal(registry.can("edit.copy", base({ inPoint: 0, outPoint: S })), true);
    for (const id of ["edit.paste", "edit.paste_overwrite", "edit.paste_track"]) {
      assert.equal(registry.can(id, base()), false, id);
      assert.equal(registry.can(id, base({ clipboard: [] })), false, id);
      assert.equal(registry.can(id, withClip()), true, id);
    }
  });

  test("paste on the current track needs a current track", () => {
    const { registry } = setup(base());
    assert.equal(registry.can("edit.paste_track", withClip({ focusTrack: null })), false);
    assert.equal(registry.can("edit.paste", withClip({ focusTrack: null })), true);
  });

  test("Mod+C sends the copy to the clipboard route, not the editor, and toasts without Undo", async () => {
    const state = base({ selection: new Set(["a1"]) });
    const h = setup(state);
    h.registry.run("edit.copy", null, state);
    assert.equal(h.sent.length, 0);
    assert.deepEqual(h.copied[0].clip_ids, ["a1"]);
    await Promise.resolve();
    assert.match(h.toasts[0][0], /^ui\.edit\.toast\.copy/);
    assert.deepEqual(h.toasts[0][1], { undo: false });
  });

  test("X is a cut that goes to the clipboard: one edit, then the list is refreshed", () => {
    const state = base({ inPoint: 2 * S, outPoint: 6 * S });
    const h = setup(state);
    h.registry.run("edit.cut", null, state);
    assert.equal(h.sent[0].op, "clipboard_cut");
    h.sent[0].done({ project, clipboard: { ok: true, entry: "e9" } });
    assert.equal(h.refreshed(), 1);
  });

  test("a cut whose copy failed tells the user in the toast, with Undo", () => {
    const state = base({ inPoint: 2 * S, outPoint: 6 * S });
    const h = setup(state);
    h.registry.run("edit.cut", null, state);
    const after = {
      ...project,
      tracks: project.tracks.map((t) => ({ ...t, clips: [clip(t.id, 0, 6)] })),
    };
    h.sent[0].done({ project: after, clipboard: { ok: false, error: "disk full" } });
    assert.match(h.toasts[0][0], /^ui\.edit\.toast\.cut_uncopied/);
    assert.match(h.toasts[0][0], /disk full/);
    assert.deepEqual(h.toasts[0][1], { undo: true });
  });

  test("Backspace never touches the clipboard: it sends a plain mute, no clipboard op", () => {
    const state = withClip({ selection: new Set(["a1"]) });
    const h = setup(state);
    h.registry.run("edit.delete", null, state);
    assert.equal(h.sent[0].op, "set_clips");
    h.sent[0].done({ project });
    assert.equal(h.refreshed(), 0);
    assert.equal(h.copied.length, 0);
  });

  test("Mod+V inserts at the play cursor, Alt+Mod+V overwrites, on the panel's target", () => {
    const state = withClip({ pasteTarget: "current" });
    const h = setup(state);
    h.registry.run("edit.paste", null, state);
    h.registry.run("edit.paste_overwrite", null, state);
    h.registry.run("edit.paste_track", null, withClip({ pasteTarget: "same" }));
    assert.deepEqual(h.sent[0].args, {
      entry_id: "e1",
      at: 4 * S,
      mode: "insert",
      target_tracks: { 0: "A" },
      group_editing: true,
    });
    assert.equal(h.sent[1].args.mode, "overwrite");
    assert.deepEqual(h.sent[2].args.target_tracks, { 0: "A" });
    assert.equal(h.sent[2].args.mode, "insert");
  });

  test("a paste that lacked recordings says so, and one that placed nothing offers no Undo", () => {
    const state = withClip();
    const h = setup(state);
    h.registry.run("edit.paste", null, state);
    h.sent[0].done({ project, clipboard: { placed: 1, missing: ["x"], entry: "e1" } });
    assert.match(h.toasts[0][0], /^ui\.edit\.toast\.paste_missing/);
    h.sent[0].done({ project, clipboard: { placed: 0, missing: ["x"], entry: "e1" } });
    assert.match(h.toasts[1][0], /^ui\.edit\.toast\.paste_nothing/);
    assert.deepEqual(h.toasts[1][1], { undo: false });
  });
});
