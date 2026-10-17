import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  autoName,
  entryTitle,
  PASTE_MODES,
  PASTE_TARGETS,
  pasteChoice,
  pasteTargets,
  shortDuration,
} from "../clipboard.js";
import { copyPlan, cutPlan, pastePlan } from "../edit-plans.js";

const S = 48000;
const clip = (id, start, seconds) => ({ id, start: start * S, length: seconds * S, muted: false });
const project = {
  rate: S,
  tracks: [
    { id: "A", name: "Anna", clips: [clip("a1", 0, 10), clip("a2", 12, 8)] },
    { id: "V", name: "Ville", clips: [clip("v1", 0, 10)] },
    { id: "M", name: "", clips: [] },
  ],
};
const entry = (extra = {}) => ({
  id: "e1",
  name: "",
  pinned: false,
  length: 5 * S,
  clips: 2,
  slots: 2,
  missing_here: 0,
  ...extra,
});
const state = (extra = {}) => ({
  project,
  selection: new Set(),
  focusTrack: "A",
  focusBus: null,
  playhead: 4 * S,
  inPoint: null,
  outPoint: null,
  groupEditing: true,
  clipboard: [entry()],
  ...extra,
});
const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;

describe("durations and names", () => {
  test("m:ss, hours when needed", () => {
    assert.equal(shortDuration(0), "0:00");
    assert.equal(shortDuration(12.4), "0:12");
    assert.equal(shortDuration(75), "1:15");
    assert.equal(shortDuration(3723), "1:02:03");
  });
  test("track name, +others, duration", () => {
    assert.equal(autoName({ trackName: "Anna", clips: 1, seconds: 12 }, t), "Anna · 0:12");
    assert.equal(autoName({ trackName: "Anna", clips: 2, seconds: 12 }, t), "Anna +1 · 0:12");
    assert.equal(autoName({ trackName: "Anna", clips: 5, seconds: 75 }, t), "Anna +4 · 1:15");
  });
  test("a track with no name gets the translated stand-in", () => {
    assert.equal(
      autoName({ trackName: "", clips: 1, seconds: 3 }, t),
      "ui.clipboard.untitled_track{} · 0:03",
    );
  });
  test("an entry shows its own name, else the automatic one from its counts", () => {
    assert.equal(entryTitle(entry({ name: "Intro" }), S, t), "Intro");
    assert.equal(
      entryTitle(entry({ name: "  " }), S, t),
      'ui.clipboard.untitled{"count":2,"duration":"0:05"}',
    );
  });
});

describe("copy", () => {
  test("selected clips: their ids and the automatic name", () => {
    const plan = copyPlan(state({ selection: new Set(["a1", "v1"]) }), t);
    assert.equal(plan.path, "copy");
    assert.deepEqual(plan.body.clip_ids, ["a1", "v1"]);
    assert.equal(plan.body.name, "Anna +1 · 0:10");
    assert.equal(plan.toast.values.count, 2);
  });
  test("the range on the current track, with the group when group editing is on", () => {
    const plan = copyPlan(state({ inPoint: 2 * S, outPoint: 6 * S }), t);
    assert.deepEqual(plan.body, {
      start: 2 * S,
      end: 6 * S,
      track_ids: ["A"],
      group_editing: true,
      name: "Anna · 0:04",
    });
  });
  test("the range wins over the selection, as for Cut", () => {
    const plan = copyPlan(state({ selection: new Set(["v1"]), inPoint: 0, outPoint: 3 * S }), t);
    assert.equal(plan.body.clip_ids, undefined);
    assert.equal(plan.body.start, 0);
  });
  test("a range with no current track and no selection has nothing to copy", () => {
    assert.equal(copyPlan(state({ focusTrack: null, inPoint: 0, outPoint: 3 * S }), t), null);
  });
  test("nothing selected, no range: nothing to copy", () => {
    assert.equal(copyPlan(state(), t), null);
    assert.equal(copyPlan({ project: null, selection: new Set() }, t), null);
  });
});

describe("paste", () => {
  test("Mod+V: the newest entry, inserted at the play cursor on the same tracks", () => {
    const plan = pastePlan(state());
    assert.equal(plan.op, "clipboard_paste");
    assert.deepEqual(plan.args, {
      entry_id: "e1",
      at: 4 * S,
      mode: "insert",
      target_tracks: null,
    });
    assert.match(plan.label.key, /paste$/);
  });
  test("overwrite is its own mode, label and toast", () => {
    const plan = pastePlan(state(), { mode: "overwrite" });
    assert.equal(plan.args.mode, "overwrite");
    assert.match(plan.label.key, /paste_overwrite$/);
    assert.match(plan.toast.key, /paste_overwrite$/);
  });
  test("the entry picked in the panel wins over the newest", () => {
    const s = state({ clipboard: [entry(), entry({ id: "e0" })], clipboardSelected: "e0" });
    assert.equal(pastePlan(s).args.entry_id, "e0");
  });
  test("a stale pick falls back to the newest", () => {
    assert.equal(pastePlan(state({ clipboardSelected: "gone" })).args.entry_id, "e1");
  });
  test("on the current track: slots land on it and the tracks below", () => {
    const plan = pastePlan(state({ focusTrack: "A" }), { target: "current" });
    assert.deepEqual(plan.args.target_tracks, { 0: "A", 1: "V" });
  });
  test("too few tracks below: the rest land on the last one", () => {
    const plan = pastePlan(state({ focusTrack: "M" }), { target: "current" });
    assert.deepEqual(plan.args.target_tracks, { 0: "M", 1: "M" });
  });
  test("no current track: no paste on the current track", () => {
    assert.equal(pastePlan(state({ focusTrack: null }), { target: "current" }), null);
    assert.notEqual(pastePlan(state({ focusTrack: null })), null);
  });
  test("an empty clipboard, no project or no play cursor: nothing to paste", () => {
    assert.equal(pastePlan(state({ clipboard: [] })), null);
    assert.equal(pastePlan(state({ clipboard: undefined })), null);
    assert.equal(pastePlan(state({ project: null })), null);
    assert.equal(pastePlan(state({ playhead: Number.NaN })), null);
  });
  test("a toast variant reports missing recordings and an empty result", () => {
    const plan = pastePlan(state());
    assert.equal(plan.toast.variant({ clipboard: { placed: 2, missing: [] } }), null);
    const missing = plan.toast.variant({ clipboard: { placed: 1, missing: ["x", "y"] } });
    assert.match(missing.key, /paste_missing$/);
    assert.equal(missing.values.count, 2);
    const none = plan.toast.variant({ clipboard: { placed: 0, missing: ["x"] } });
    assert.match(none.key, /paste_nothing$/);
    assert.equal(none.undo, false);
  });
});

describe("the mode and target choice", () => {
  test("defaults: insert on the same tracks", () => {
    assert.deepEqual(pasteChoice({}), { mode: "insert", target: "same" });
  });
  test("remembers valid values and ignores nonsense", () => {
    assert.deepEqual(pasteChoice({ pasteMode: "overwrite", pasteTarget: "current" }), {
      mode: "overwrite",
      target: "current",
    });
    assert.deepEqual(pasteChoice({ pasteMode: "sideways", pasteTarget: 7 }), {
      mode: "insert",
      target: "same",
    });
  });
  test("the four forms are the modes times the targets", () => {
    assert.deepEqual(PASTE_MODES, ["insert", "overwrite"]);
    assert.deepEqual(PASTE_TARGETS, ["same", "current"]);
  });
  test("pasteTargets maps slots onto consecutive tracks and clamps", () => {
    const ids = ["A", "V", "M"];
    assert.deepEqual(pasteTargets(1, ids, "V"), { 0: "V" });
    assert.deepEqual(pasteTargets(3, ids, "V"), { 0: "V", 1: "M", 2: "M" });
    assert.equal(pasteTargets(1, ids, "nobody"), null);
  });
});

describe("cut names its entry like copy does", () => {
  test("clipboard_cut carries the range, the group flag and the automatic name", () => {
    const plan = cutPlan(state({ inPoint: 2 * S, outPoint: 6 * S }), { t });
    assert.equal(plan.op, "clipboard_cut");
    assert.deepEqual(plan.args, {
      start: 2 * S,
      end: 6 * S,
      track_ids: ["A"],
      group_editing: true,
      name: "Anna · 0:04",
    });
  });
  test("the toast says when the clipboard copy failed, and still offers Undo", () => {
    const plan = cutPlan(state({ inPoint: 2 * S, outPoint: 6 * S }), { t });
    assert.equal(plan.toast.variant({ clipboard: { ok: true } }), null);
    const failed = plan.toast.variant({ clipboard: { ok: false, error: "disk full" } });
    assert.match(failed.key, /cut_uncopied$/);
    assert.equal(failed.values.error, "disk full");
    assert.notEqual(failed.undo, false);
  });
});
