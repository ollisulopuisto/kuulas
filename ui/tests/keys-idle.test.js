// Edit keys never fail silently (owner, 2026-10-21/22): a key that cannot act says why, the
// browser's beep never sounds for it, the keys work from every panel but text fields and modal
// dialogs, and after an edit from a side panel the timeline has the focus again.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { createKeymap } from "../keys.js";

const press = (over) => ({
  key: "",
  code: "",
  shiftKey: false,
  altKey: false,
  ctrlKey: false,
  metaKey: false,
  repeat: false,
  target: { tagName: "DIV" },
  prevented: false,
  preventDefault() {
    this.prevented = true;
  },
  getModifierState: () => false,
  ...over,
});
const X = { key: "x", code: "KeyX" };
const field = { tagName: "INPUT", type: "text" };

const EDIT_IDS = [
  "edit.remove",
  "edit.remove_track",
  "edit.cut",
  "edit.cut_track",
  "edit.lift_cut",
  "edit.close_gap_all",
  "edit.remove_clips",
  "edit.delete",
  "edit.copy",
  "edit.split",
  "edit.split_all",
  "clip.quick_mute",
  "clip.mute",
  "clip.fade",
  "edit.trim_start",
  "edit.trim_end",
];

/**
 * The real default keymap; the edit commands cannot act (`can` false) unless `canRun` lists them,
 * and they explain themselves with a fixed reason.
 */
function setup({ context = "timeline", canRun = [], modal = false, platform = "other" } = {}) {
  const calls = [];
  const idle = [];
  const edited = [];
  const registry = createRegistry();
  for (const entry of DEFAULT_KEYMAP) {
    const edit = EDIT_IDS.includes(entry.id);
    registry.register(entry.id, () => calls.push(entry.id), {
      can: edit ? () => canRun.includes(entry.id) : null,
      why: edit ? () => ({ key: `why.${entry.id}` }) : null,
    });
  }
  const keymap = createKeymap({
    platform,
    getContext: () => context,
    registry,
    getState: () => ({}),
    onIdle: (reason, event) => idle.push([reason, event]),
    onEdited: (id, ctx) => edited.push([id, ctx]),
    isModal: () => modal,
  });
  keymap.setEntries(resolveKeymap(DEFAULT_KEYMAP, {}, platform));
  return { keymap, calls, idle, edited };
}

describe("a key that cannot act says why instead of beeping", () => {
  test("X with nothing marked: handled, default prevented, the reason shown, nothing run", () => {
    const { keymap, calls, idle } = setup();
    const event = press(X);
    assert.equal(keymap.handle(event), true);
    assert.equal(event.prevented, true);
    assert.deepEqual(calls, []);
    assert.deepEqual(
      idle.map(([reason]) => reason),
      [{ key: "why.edit.remove" }],
    );
  });

  test("the same for Backspace, Mod+X, Alt+X, Alt+Mod+X, Mod+C, B, H and G", () => {
    const keys = [
      [{ key: "Backspace", code: "Backspace" }, "edit.delete"],
      [{ key: "x", code: "KeyX", ctrlKey: true }, "edit.cut"],
      [{ key: "x", code: "KeyX", altKey: true }, "edit.lift_cut"],
      [{ key: "x", code: "KeyX", altKey: true, ctrlKey: true }, "edit.close_gap_all"],
      [{ key: "c", code: "KeyC", ctrlKey: true }, "edit.copy"],
      [{ key: "b", code: "KeyB" }, "edit.split"],
      [{ key: "h", code: "KeyH" }, "clip.quick_mute"],
      [{ key: "g", code: "KeyG" }, "clip.fade"],
    ];
    for (const [over, id] of keys) {
      const { keymap, idle } = setup();
      const event = press(over);
      assert.equal(keymap.handle(event), true, id);
      assert.equal(event.prevented, true, id);
      assert.equal(idle[0]?.[0].key, `why.${id}`, id);
    }
  });

  test("a held key is swallowed too, but the notice is not repeated", () => {
    const { keymap, idle } = setup();
    const event = press({ ...X, repeat: true });
    assert.equal(keymap.handle(event), true);
    assert.equal(event.prevented, true);
    assert.deepEqual(idle, []);
  });

  test("a key that can act just runs: no reason, no notice", () => {
    const { keymap, calls, idle } = setup({ canRun: ["edit.remove"] });
    assert.equal(keymap.handle(press(X)), true);
    assert.deepEqual(calls, ["edit.remove"]);
    assert.deepEqual(idle, []);
  });

  test("in a text field the key stays the field's", () => {
    const { keymap, idle } = setup();
    const event = press({ ...X, target: field });
    assert.equal(keymap.handle(event), false);
    assert.equal(event.prevented, false);
    assert.deepEqual(idle, []);
  });

  test("a key that is no edit key and cannot act stays unhandled", () => {
    const { keymap, idle } = setup();
    const event = press({ key: "F9", code: "F9" });
    assert.equal(keymap.handle(event), false);
    assert.equal(event.prevented, false);
    assert.deepEqual(idle, []);
  });

  test("with a modal dialog open the editing keys are left alone", () => {
    const { keymap, calls, idle } = setup({ modal: true, canRun: ["edit.remove"] });
    const event = press(X);
    assert.equal(keymap.handle(event), false);
    assert.equal(event.prevented, false);
    assert.deepEqual(calls, []);
    assert.deepEqual(idle, []);
  });
});

describe("the editing keys work from every panel but text fields and dialogs", () => {
  test("from the side panels, the Markers tab and the Candidates tab", () => {
    for (const context of ["side", "markers", "candidates", "timeline"]) {
      for (const [over, id] of [
        [{ key: "b", code: "KeyB" }, "edit.split"],
        [{ key: "h", code: "KeyH" }, "clip.quick_mute"],
        [{ key: "x", code: "KeyX" }, "edit.remove"],
        [{ key: "x", code: "KeyX", altKey: true }, "edit.lift_cut"],
        [{ key: "c", code: "KeyC", ctrlKey: true }, "edit.copy"],
        [{ key: "q", code: "KeyQ" }, "edit.trim_start"],
        [{ key: "m", code: "KeyM" }, "clip.mute"],
      ]) {
        const { keymap, calls } = setup({ context, canRun: [id] });
        assert.equal(keymap.handle(press(over)), true, `${id} in ${context}`);
        assert.deepEqual(calls, [id], `${id} in ${context}`);
      }
    }
  });

  test("Backspace deletes from the side panels; the Candidates tab and the transcript keep it", () => {
    const side = setup({ context: "side", canRun: ["edit.delete"] });
    side.keymap.handle(press({ key: "Backspace", code: "Backspace" }));
    assert.deepEqual(side.calls, ["edit.delete"]);
    const markers = setup({ context: "markers", canRun: ["edit.delete"] });
    markers.keymap.handle(press({ key: "Backspace", code: "Backspace" }));
    assert.deepEqual(markers.calls, ["edit.delete"]);
    const candidates = setup({ context: "candidates", canRun: ["edit.delete"] });
    candidates.keymap.handle(press({ key: "Backspace", code: "Backspace" }));
    assert.deepEqual(candidates.calls, ["candidate.apply"]);
    const transcript = setup({ context: "transcript", canRun: ["edit.delete"] });
    transcript.keymap.handle(press({ key: "Backspace", code: "Backspace" }));
    assert.deepEqual(transcript.calls, ["transcript.delete_words"]);
  });

  test("in the transcript X and Mod+X keep their word meaning", () => {
    const x = setup({ context: "transcript", canRun: ["edit.remove"] });
    x.keymap.handle(press(X));
    assert.deepEqual(x.calls, ["transcript.remove_words"]);
    const cut = setup({ context: "transcript", canRun: ["edit.cut"] });
    cut.keymap.handle(press({ ...X, ctrlKey: true }));
    assert.deepEqual(cut.calls, ["transcript.cut_words"]);
  });

  test("a blocked edit key in the transcript falls to the transcript, not to a notice", () => {
    const { keymap, idle } = setup({ context: "transcript" });
    keymap.handle(press(X));
    assert.deepEqual(idle, []);
  });
});

describe("after an edit key from a side panel the timeline gets the focus", () => {
  test("from the side panels, Markers and Candidates, once the key ran", () => {
    for (const context of ["side", "markers", "candidates"]) {
      const { keymap, edited } = setup({ context, canRun: ["edit.split"] });
      keymap.handle(press({ key: "b", code: "KeyB" }));
      assert.deepEqual(edited, [["edit.split", context]], context);
    }
  });

  test("not from the timeline, and not when the key could not act", () => {
    const timeline = setup({ context: "timeline", canRun: ["edit.split"] });
    timeline.keymap.handle(press({ key: "b", code: "KeyB" }));
    assert.deepEqual(timeline.edited, []);
    const idle = setup({ context: "side" });
    idle.keymap.handle(press({ key: "b", code: "KeyB" }));
    assert.deepEqual(idle.edited, []);
  });
});
