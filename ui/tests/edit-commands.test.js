import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { registerEditCommands } from "../edit-commands.js";
import { dropPastePlan } from "../edit-plans.js";
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
  rangeMode: "all",
  trackSelection: new Set(),
  ...extra,
});

function setup(state, previewAnswer = { started: true, missing: 0 }) {
  const registry = createRegistry();
  const sent = [];
  const patches = [];
  const toasts = [];
  const copied = [];
  const previewed = [];
  const cleared = [];
  const shared = [];
  const shown = [];
  const opened = [];
  const sentToWindow = [];
  const carted = [];
  const seeks = [];
  let refreshed = 0;
  let renamed = 0;
  let now = 1000;
  registerEditCommands(registry, {
    t: (key, values = {}) => `${key}${JSON.stringify(values)}`,
    formatSeconds: (value) => String(value),
    app: {
      getState: () => state,
      patch: (p) => patches.push(p),
      seek: (frame) => seeks.push(frame),
      edit: (change) => sent.push(change),
      toast: (text, options) => toasts.push([text, options]),
      now: () => now,
      copy: (body) => {
        copied.push(body);
        return Promise.resolve(true);
      },
      focusName: () => {
        renamed += 1;
      },
      previewClipboard: (id) => {
        previewed.push(id);
        return Promise.resolve(previewAnswer);
      },
      refreshClipboard: () => {
        refreshed += 1;
      },
      clearOldClipboard: (keep) => {
        cleared.push(keep);
        return Promise.resolve(0);
      },
      shareClipboard: (id, on) => {
        shared.push([id, on]);
        return Promise.resolve();
      },
      showClipboard: (view) => {
        shown.push(view);
      },
      openClipboardProject: () => {
        opened.push(true);
      },
      setCartSlot: (id, slot) => {
        carted.push([id, slot]);
        return Promise.resolve();
      },
      sendToWindow: (entry) => {
        sentToWindow.push(entry);
        return Promise.resolve();
      },
    },
  });
  return {
    registry,
    copied,
    seeks,
    previewed,
    cleared,
    shared,
    shown,
    opened,
    sentToWindow,
    carted,
    refreshed: () => refreshed,
    renamed: () => renamed,
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
  "edit.remove",
  "edit.remove_track",
  "edit.cut",
  "edit.cut_track",
  "edit.lift_cut",
  "edit.close_gap_all",
  "clip.mute",
  "track.mute",
  "track.solo",
  "track.solo_add",
  "track.cycle_kind",
  "range.scope_toggle",
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
  "edit.paste_insert",
  "edit.paste_track",
  "edit.paste_same",
  "edit.paste_insert_track",
  "edit.paste_insert_same",
  "edit.preview_clipboard",
  "edit.clear_old_clipboard",
  "edit.share_clipboard",
  "clipboard.view_project",
  "clipboard.view_shared",
  "clipboard.view_others",
  "clipboard.open_project",
  "clipboard.send_to_window",
  ...[1, 2, 3, 4, 5, 6, 7].flatMap((n) => [
    `clipboard.cart_play_${n}`,
    `clipboard.cart_assign_${n}`,
  ]),
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

  test("Alt+Mod+K cycles the focused track's kind: one set_track edit and a toast", () => {
    const keys = DEFAULT_KEYMAP.find((e) => e.id === "track.cycle_kind").keys;
    assert.deepEqual(keys, { mac: "Alt+Mod+K", other: "Alt+Mod+K" });
    const state = base({
      project: { ...project, tracks: [{ id: "A", name: "Anna", kind: "music", clips: [] }] },
    });
    const h = setup(state);
    assert.equal(h.registry.run("track.cycle_kind", null, state), true);
    assert.equal(h.sent.length, 1);
    assert.deepEqual(h.sent[0].args, { track_id: "A", kind: "speech" });
    h.sent[0].done({ project: state.project });
    assert.match(h.toasts[0][0], /^ui\.edit\.toast\.track_kind\.speech/);
  });

  test("Alt+X is lift-cut and Alt+Mod+X closes the gap on all tracks", () => {
    const keysOf = (id) => DEFAULT_KEYMAP.find((e) => e.id === id).keys;
    assert.deepEqual(keysOf("edit.lift_cut"), { mac: "Alt+X", other: "Alt+X" });
    assert.deepEqual(keysOf("edit.close_gap_all"), { mac: "Alt+Mod+X", other: "Alt+Mod+X" });
  });

  test("lift-cut sends one clipboard_lift_cut edit and refreshes the list; Backspace stays off the clipboard", () => {
    const state = base({ inPoint: 2 * S, outPoint: 6 * S });
    const h = setup(state);
    h.registry.run("edit.lift_cut", null, state);
    assert.equal(h.sent.length, 1);
    assert.equal(h.sent[0].op, "clipboard_lift_cut");
    assert.match(h.sent[0].label, /^ui\.edit\.label\.lift_cut/);
    h.sent[0].done({ project, clipboard: { ok: true, entry: "e9" } });
    assert.equal(h.refreshed(), 1);
  });

  test("a finished cut takes the range away from the screen: marks, range tracks, selection", () => {
    for (const id of [
      "edit.remove",
      "edit.cut",
      "edit.cut_track",
      "edit.lift_cut",
      "edit.close_gap_all",
    ]) {
      const state = base({ inPoint: 2 * S, outPoint: 6 * S });
      const h = setup(state);
      h.registry.run(id, null, state);
      assert.deepEqual(h.patches, [], `${id}: nothing is cleared before the edit is done`);
      h.sent[0].done({ project, clipboard: { ok: true, entry: "e9" } });
      assert.deepEqual(h.patches.at(-1), {
        inPoint: null,
        outPoint: null,
        rangeTracks: new Set(),
        selection: new Set(),
      });
    }
  });

  test("after a ripple cut the play cursor goes to the splice, so P plays the join", () => {
    for (const id of ["edit.remove", "edit.cut", "edit.close_gap_all"]) {
      const state = base({ inPoint: 2 * S, outPoint: 6 * S, playhead: 9 * S });
      const h = setup(state);
      h.registry.run(id, null, state);
      assert.deepEqual(h.seeks, [], `${id}: not before the edit is done`);
      h.sent[0].done({ project, clipboard: { ok: true, entry: "e9" } });
      assert.deepEqual(h.seeks, [2 * S], id);
    }
  });

  test("lift-cut and soft delete leave the cursor where it is", () => {
    for (const id of ["edit.lift_cut", "edit.delete"]) {
      const state = base({ inPoint: 2 * S, outPoint: 6 * S, playhead: 9 * S });
      const h = setup(state);
      h.registry.run(id, null, state);
      h.sent[0].done?.({ project, clipboard: { ok: true, entry: "e9" } });
      assert.deepEqual(h.seeks, [], id);
    }
  });

  test("Backspace (soft delete) keeps the range", () => {
    const state = base({ inPoint: 2 * S, outPoint: 6 * S });
    const h = setup(state);
    h.registry.run("edit.delete", null, state);
    h.sent[0].done?.({ project });
    assert.deepEqual(h.patches, []);
  });

  test("close gap on all tracks is a plain ripple_delete, no clipboard op", () => {
    const state = base({ inPoint: 2 * S, outPoint: 6 * S });
    const h = setup(state);
    h.registry.run("edit.close_gap_all", null, state);
    assert.equal(h.sent[0].op, "ripple_delete");
    assert.equal(h.refreshed(), 0);
  });

  test("G fades at the play cursor: set_fade_at on the clip under it, one step, a toast with Undo", () => {
    const state = base({ playhead: 1 * S });
    const h = setup(state);
    assert.equal(h.registry.status("clip.fade"), "ready");
    assert.equal(h.registry.run("clip.fade", null, state), true);
    assert.equal(h.sent.length, 1);
    assert.equal(h.sent[0].op, "set_fade_at");
    assert.deepEqual(h.sent[0].args, { clip_id: "a1", frame: 1 * S });
    assert.match(h.sent[0].label, /^ui\.edit\.label\.fade/);
    h.sent[0].done({ project });
    assert.match(h.toasts[0][0], /^ui\.edit\.toast\.fade/);
    assert.deepEqual(h.toasts[0][1], { undo: true });
  });

  test("fade is disabled with no clip under the play cursor", () => {
    const h = setup(base());
    assert.equal(h.registry.can("clip.fade", base({ playhead: 20 * S })), false);
    assert.equal(h.registry.can("clip.fade", base({ focusTrack: null })), false);
    assert.equal(h.registry.run("clip.fade", null, base({ playhead: 20 * S })), false);
    assert.equal(h.sent.length, 0);
  });

  test("each is disabled when there is nothing to act on", () => {
    const { registry } = setup(base());
    const empty = base({ focusTrack: null });
    for (const id of [
      "edit.delete",
      "edit.cut",
      "edit.cut_track",
      "edit.lift_cut",
      "edit.close_gap_all",
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
    assert.equal(registry.can("range.scope_toggle", empty), true);
    assert.equal(registry.can("range.scope_toggle", { project: null }), false);
  });

  test("split sends split_clips with a translated label and a toast with Undo after the answer", () => {
    const h = setup(base());
    assert.equal(h.registry.run("edit.split", null, base()), true);
    assert.equal(h.sent.length, 1);
    assert.equal(h.sent[0].op, "split_clips");
    assert.match(h.sent[0].label, /^ui\.edit\.label\.split/);
    assert.equal(typeof h.sent[0].provisional, "function"); // shows at once, before the answer
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

  test("a range command in selected-only mode with no track selected says why, and sends nothing", () => {
    const state = base({ inPoint: 0, outPoint: 3 * S, rangeMode: "selected" });
    const h = setup(state);
    assert.equal(h.registry.can("edit.delete", state), true);
    h.registry.run("edit.delete", null, state);
    assert.equal(h.sent.length, 0);
    assert.match(h.toasts[0][0], /^ui\.scope\.none_selected/);
    assert.deepEqual(h.toasts[0][1], { undo: false });
  });

  test("select all picks the clip ids; E flips the range scope", () => {
    const state = base();
    const h = setup(state);
    h.registry.run("edit.select_all", null, state);
    assert.deepEqual([...h.patches[0].selection], ["a1", "v1"]);
    h.registry.run("range.scope_toggle", null, state);
    assert.deepEqual(h.patches[1], { rangeMode: "selected" });
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
    for (const id of ["edit.paste", "edit.paste_insert", "edit.paste_track"]) {
      assert.equal(registry.can(id, base()), false, id);
      assert.equal(registry.can(id, base({ clipboard: [] })), false, id);
      assert.equal(registry.can(id, withClip()), true, id);
    }
  });

  test("the four paste forms are fixed commands whatever the panel's choice says", () => {
    const state = withClip({ pasteTarget: "current", pasteMode: "overwrite" });
    const h = setup(state);
    h.registry.run("edit.paste_insert_same", null, state);
    h.registry.run("edit.paste_insert_track", null, state);
    h.registry.run("edit.paste_same", null, state);
    assert.equal(h.sent[0].args.mode, "insert");
    // the source track by name, else track 1 (slots are dense, so the slot number is no track)
    assert.deepEqual(h.sent[0].args.target_tracks, { 0: "A" });
    assert.equal(h.sent[1].args.mode, "insert");
    assert.deepEqual(h.sent[1].args.target_tracks, { 0: "A" });
    assert.equal(h.sent[2].args.mode, "overwrite");
    assert.deepEqual(h.sent[2].args.target_tracks, { 0: "A" });
    assert.equal(h.registry.can("edit.paste_insert_track", withClip({ focusTrack: null })), false);
    assert.equal(h.registry.can("edit.paste_same", withClip({ focusTrack: null })), true);
  });

  test("Preview plays the picked (else newest) entry without an edit", async () => {
    const state = withClip();
    const h = setup(state);
    assert.equal(h.registry.can("edit.preview_clipboard", base()), false);
    assert.equal(h.registry.can("edit.preview_clipboard", state), true);
    h.registry.run("edit.preview_clipboard", null, state);
    assert.deepEqual(h.previewed, ["e1"]);
    assert.equal(h.sent.length, 0);
    await Promise.resolve();
    assert.equal(h.toasts.length, 0);
  });

  test("Clear old entries keeps the count the Clipboard tab names, 100 by default", () => {
    const state = withClip();
    const h = setup(state);
    assert.equal(h.registry.can("edit.clear_old_clipboard", base()), false); // nothing on it
    assert.equal(h.registry.can("edit.clear_old_clipboard", state), true);
    h.registry.run("edit.clear_old_clipboard", null, state);
    assert.deepEqual(h.cleared, [100]);
    assert.equal(h.sent.length, 0); // not an edit: no undo step
    const named = setup({ ...state, clipboardKeep: 7 });
    named.registry.run("edit.clear_old_clipboard", null, state);
    assert.deepEqual(named.cleared, [7]);
  });

  test("Share toggles the picked (else newest) entry and changes no project", () => {
    const state = withClip();
    const h = setup(state);
    assert.equal(h.registry.can("edit.share_clipboard", base()), false);
    assert.equal(h.registry.can("edit.share_clipboard", state), true);
    h.registry.run("edit.share_clipboard", null, state);
    assert.deepEqual(h.shared, [["e1", true]]);
    const on = setup({
      ...state,
      clipboard: [{ ...state.clipboard[0], shared: true }],
    });
    on.registry.run("edit.share_clipboard", null, state);
    assert.deepEqual(on.shared, [["e1", false]]);
    assert.equal(h.sent.length, 0);
  });

  test("Copy to other window needs another window; it shows greyed out until there is one", () => {
    const state = withClip();
    const h = setup(state);
    for (const otherWindows of [null, 0, undefined]) {
      assert.equal(h.registry.can("clipboard.send_to_window", { ...state, otherWindows }), false);
    }
    assert.equal(h.registry.can("clipboard.send_to_window", { ...state, otherWindows: 1 }), true);
    assert.equal(
      h.registry.can("clipboard.send_to_window", { ...base(), otherWindows: 1, clipboard: [] }),
      false,
      "nothing to copy or send",
    );
    assert.equal(
      h.registry.can("clipboard.send_to_window", { ...base({ project: null }), otherWindows: 1 }),
      false,
    );
  });

  test("Copy to other window sends the picked (else newest) entry when nothing is selected", async () => {
    const state = { ...withClip(), otherWindows: 1 };
    const h = setup(state);
    await h.registry.run("clipboard.send_to_window", null, state);
    assert.deepEqual(
      h.sentToWindow.map((entry) => entry.id),
      ["e1"],
    );
    assert.equal(h.sent.length, 0); // not an edit: no undo step
  });

  test("Alt+n plays the entry that holds cart slot n; an empty slot says so", () => {
    const state = withClip({
      clipboard: [
        { ...entry, id: "q1", cart: 2 },
        { ...entry, id: "q2" },
      ],
    });
    const h = setup(state);
    h.registry.run("clipboard.cart_play_2", null, state);
    assert.deepEqual(h.previewed, ["q1"]);
    assert.equal(h.sent.length, 0); // not an edit
    h.registry.run("clipboard.cart_play_5", null, state);
    assert.deepEqual(h.previewed, ["q1"]);
    assert.match(h.toasts.at(-1)[0], /ui\.cart\.empty/);
  });

  test("Shift+Alt+n gives the picked (else first) entry cart slot n", () => {
    const state = withClip({
      clipboard: [
        { ...entry, id: "q1" },
        { ...entry, id: "q2" },
      ],
    });
    const h = setup(state);
    h.registry.run("clipboard.cart_assign_4", null, state);
    assert.deepEqual(h.carted, [["q1", 4]]);
    const picked = { ...state, clipboardSelected: "q2" };
    const second = setup(picked);
    second.registry.run("clipboard.cart_assign_1", null, picked);
    assert.deepEqual(second.carted, [["q2", 1]]);
    assert.equal(h.registry.can("clipboard.cart_assign_1", base()), false, "nothing to give");
    assert.equal(h.registry.can("clipboard.cart_play_1", base({ project: null })), false);
  });

  test("the clipboard views and Open a project are commands", () => {
    const state = withClip();
    const h = setup(state);
    for (const view of ["project", "shared", "others"]) {
      h.registry.run(`clipboard.view_${view}`, null, state);
    }
    assert.deepEqual(h.shown, ["project", "shared", "others"]);
    h.registry.run("clipboard.open_project", null, state);
    assert.equal(h.opened.length, 1);
    assert.equal(h.registry.can("clipboard.view_shared", base({ project: null })), false);
  });

  test("a preview with nothing to hear says so, without Undo", async () => {
    const state = withClip();
    const h = setup(state, { started: false });
    h.registry.run("edit.preview_clipboard", null, state);
    await Promise.resolve();
    await Promise.resolve();
    assert.match(h.toasts[0][0], /^ui\.clipboard\.preview_nothing/);
    assert.deepEqual(h.toasts[0][1], { undo: false });
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

  test("Mod+V overwrites at the play cursor, Alt+Mod+V inserts, on the panel's target", () => {
    const state = withClip({ pasteTarget: "current" });
    const h = setup(state);
    h.registry.run("edit.paste", null, state);
    h.registry.run("edit.paste_insert", null, state);
    h.registry.run("edit.paste_track", null, withClip({ pasteTarget: "same" }));
    assert.deepEqual(h.sent[0].args, {
      entry_id: "e1",
      at: 4 * S,
      mode: "overwrite",
      target_tracks: { 0: "A" },
    });
    assert.equal(h.sent[1].args.mode, "insert");
    assert.deepEqual(h.sent[2].args.target_tracks, { 0: "A" });
    assert.equal(h.sent[2].args.mode, "overwrite");
  });

  test("with In and Out marked every paste form starts at In and stops at Out", () => {
    const state = withClip({ inPoint: S, outPoint: 2 * S });
    const h = setup(state);
    h.registry.run("edit.paste", null, state);
    h.registry.run("edit.paste_insert", null, state);
    for (const sent of h.sent) {
      assert.equal(sent.args.at, S);
      assert.equal(sent.args.out, 2 * S);
    }
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

describe("buses (add_bus)", () => {
  test("both commands are in the keymap, unbound, and ready", () => {
    const { registry } = setup(base());
    for (const id of ["track.group_into_bus", "track.new_bus"]) {
      const entry = DEFAULT_KEYMAP.find((e) => e.id === id);
      assert.deepEqual(entry.keys, { mac: null, other: null }, id);
      assert.equal(registry.status(id), "ready", id);
    }
  });

  test("grouping sends add_bus with the tracks of the selected clips, in track order", () => {
    const h = setup(base({ selection: new Set(["v1", "a1"]), focusTrack: null }));
    h.registry.run("track.group_into_bus");
    assert.equal(h.sent.length, 1);
    assert.equal(h.sent[0].op, "add_bus");
    assert.deepEqual(h.sent[0].args, { track_ids: ["A", "V"] });
  });

  test("with no selection the focused track counts", () => {
    const h = setup(base({ focusTrack: "V" }));
    h.registry.run("track.group_into_bus");
    assert.deepEqual(h.sent[0].args, { track_ids: ["V"] });
  });

  test("grouping needs a track; a new empty bus needs only a project", () => {
    const state = base({ focusTrack: null });
    const none = setup(state);
    assert.equal(none.registry.can("track.group_into_bus", state), false);
    assert.equal(none.registry.can("track.new_bus", state), true);
    none.registry.run("track.new_bus");
    assert.deepEqual(none.sent[0].args, {});
  });

  test("the new bus is focused and renamed once the server answers", () => {
    const h = setup(base());
    h.registry.run("track.new_bus");
    h.sent[0].done({ project: { buses: [{ id: "b1" }, { id: "b9" }] } });
    assert.deepEqual(h.patches.at(-1), { focusBus: "b9", focusTrack: null });
    assert.equal(h.renamed(), 1);
  });
});

describe("a drop from the Clipboard tab", () => {
  test("registerEditCommands hands back send: the drop is one paste edit with the paste's toasts", () => {
    const registry = createRegistry();
    const sent = [];
    const toasts = [];
    let refreshed = 0;
    const { send } = registerEditCommands(registry, {
      t: (key, values = {}) => `${key}${JSON.stringify(values)}`,
      formatSeconds: String,
      app: {
        getState: () => base(),
        patch: () => {},
        edit: (change) => sent.push(change),
        toast: (text, options) => toasts.push([text, options]),
        refreshClipboard: () => {
          refreshed += 1;
        },
      },
    });
    send(dropPastePlan({ id: "e1", clips: 2 }, { at: 5 * S, targetTracks: { 0: "A" } }, "insert"));
    assert.equal(sent.length, 1);
    assert.equal(sent[0].op, "clipboard_paste");
    assert.deepEqual(sent[0].args, {
      entry_id: "e1",
      at: 5 * S,
      mode: "insert",
      target_tracks: { 0: "A" },
    });
    assert.equal(sent[0].label, "ui.edit.label.paste_insert{}");
    sent[0].done({ clipboard: { placed: 2, missing: ["x"] }, project });
    assert.equal(toasts[0][0], 'ui.edit.toast.paste_missing{"count":1}');
    assert.equal(refreshed, 1);
  });
});
