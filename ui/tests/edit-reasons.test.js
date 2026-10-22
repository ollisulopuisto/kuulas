import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { registerEditCommands } from "../edit-commands.js";
import * as plans from "../edit-plans.js";
import { EDIT_KEY_IDS, idleReason } from "../edit-reasons.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";

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
  clipboard: [],
  ...extra,
});
const keyOf = (id, s) => idleReason(id, s)?.key ?? null;

describe("why an edit key does nothing", () => {
  test("without a project every edit key says so", () => {
    for (const id of ["edit.remove", "edit.split", "edit.delete", "edit.cut", "clip.quick_mute"]) {
      assert.equal(keyOf(id, state({ project: null })), "ui.edit.idle.no_project", id);
    }
  });

  test("X, Mod+X, Alt+X, close gap, Backspace and copy name the missing range or clips", () => {
    assert.equal(keyOf("edit.remove", state()), "ui.edit.idle.remove");
    assert.equal(keyOf("edit.remove_track", state()), "ui.edit.idle.remove");
    assert.equal(keyOf("edit.cut", state()), "ui.edit.idle.cut");
    assert.equal(keyOf("edit.cut_track", state()), "ui.edit.idle.cut");
    assert.equal(keyOf("edit.lift_cut", state()), "ui.edit.idle.cut");
    assert.equal(keyOf("edit.close_gap_all", state()), "ui.edit.idle.close_gap");
    assert.equal(keyOf("edit.delete", state()), "ui.edit.idle.delete");
    assert.equal(keyOf("edit.copy", state()), "ui.edit.idle.copy");
    assert.equal(keyOf("edit.remove_clips", state()), "ui.edit.idle.remove_clips");
  });

  test("Backspace on clips that are all muted already says so", () => {
    const muted = {
      ...project,
      tracks: [{ ...project.tracks[0], clips: [clip("a1", 0, 10, { muted: true })] }],
    };
    assert.equal(
      keyOf("edit.delete", state({ project: muted, selection: new Set(["a1"]) })),
      "ui.edit.idle.delete_muted",
    );
  });

  test("Mod+C on a range with no audio under it says so", () => {
    const s = state({ inPoint: 30 * S, outPoint: 40 * S });
    assert.equal(
      plans.copyPlan(s, (k) => k),
      null,
    );
    assert.equal(keyOf("edit.copy", s), "ui.edit.idle.copy_empty");
  });

  test("split, trim and fade want the play cursor inside a clip", () => {
    const off = state({ playhead: 11 * S });
    assert.equal(keyOf("edit.split", off), "ui.edit.idle.split");
    assert.equal(keyOf("edit.split_all", off), "ui.edit.idle.split_all");
    assert.equal(keyOf("edit.trim_start", off), "ui.edit.idle.trim");
    assert.equal(keyOf("edit.trim_end", off), "ui.edit.idle.trim");
    assert.equal(keyOf("clip.fade", off), "ui.edit.idle.fade");
  });

  test("mute, nudge, gain and move want selected clips", () => {
    assert.equal(keyOf("clip.mute", state()), "ui.edit.idle.mute");
    assert.equal(keyOf("edit.nudge_left", state()), "ui.edit.idle.nudge");
    assert.equal(keyOf("clip.gain_up", state()), "ui.edit.idle.gain");
    assert.equal(keyOf("edit.move_up", state()), "ui.edit.idle.move");
    const picked = state({ selection: new Set(["a1"]) });
    assert.equal(keyOf("edit.move_up", picked), "ui.edit.idle.move_first");
    const single = { ...project, tracks: [project.tracks[0]] };
    assert.equal(keyOf("edit.move_down", { ...picked, project: single }), "ui.edit.idle.move_last");
  });

  test("H with no clip under the cursor says so", () => {
    assert.equal(keyOf("clip.quick_mute", state({ playhead: 11 * S })), "ui.edit.idle.quick_mute");
  });

  test("group, ungroup and merge say what they need", () => {
    const one = state({ selection: new Set(["a1"]) });
    assert.equal(keyOf("edit.group", one), "ui.edit.idle.group");
    assert.equal(keyOf("edit.ungroup", one), "ui.edit.idle.ungroup");
    assert.equal(keyOf("edit.merge", one), "ui.edit.idle.merge");
  });

  test("track keys need a track in focus; paste needs a clipboard entry", () => {
    const none = state({ focusTrack: null });
    assert.equal(keyOf("track.mute", none), "ui.edit.idle.no_track");
    assert.equal(keyOf("track.solo", none), "ui.edit.idle.no_track");
    assert.equal(keyOf("edit.paste", state()), "ui.edit.idle.paste_empty");
    assert.equal(keyOf("edit.paste_insert", state()), "ui.edit.idle.paste_empty");
  });

  test("an unexplained command falls back to a generic line", () => {
    assert.equal(keyOf("bus.mute", state()), "ui.edit.idle.generic");
  });

  test("every edit key registered carries a reason through the registry", () => {
    const registry = createRegistry();
    registerEditCommands(registry, {
      t: (k) => k,
      formatSeconds: String,
      app: { getState: () => state() },
    });
    let checked = 0;
    for (const entry of DEFAULT_KEYMAP) {
      if (!EDIT_KEY_IDS.has(entry.id)) continue;
      assert.ok(registry.has(entry.id), `${entry.id} registered`);
      assert.ok(registry.why(entry.id, state({ project: null })), `${entry.id} explains itself`);
      checked += 1;
    }
    assert.ok(checked > 20, "the list of edit keys is not empty");
  });

  test("the registry gives no reason for a command that can act", () => {
    const registry = createRegistry();
    registerEditCommands(registry, {
      t: (k) => k,
      formatSeconds: String,
      app: { getState: () => state() },
    });
    assert.equal(registry.why("edit.split", state()), null);
  });
});
