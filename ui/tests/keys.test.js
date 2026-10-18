import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import { nextPanel, PANELS } from "../focus.js";
import { resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { createKeymap, isTextField } from "../keys.js";

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
const altGr = { ctrlKey: true, altKey: true, getModifierState: (k) => k === "AltGraph" };

/** A dispatcher over the real default keymap whose commands just record their calls. */
function setup({ platform = "other", context = "timeline", overrides = {} } = {}) {
  const calls = [];
  const registry = createRegistry();
  const args = {
    "view.zoom_in": [1],
    "view.zoom_out": [-1],
    "panel.next": [1],
    "panel.previous": [-1],
  };
  for (const entry of DEFAULT_KEYMAP) {
    registry.register(entry.id, () => calls.push([entry.id, ...(args[entry.id] ?? [])]));
  }
  const keymap = createKeymap({ platform, getContext: () => context, registry });
  keymap.setEntries(resolveKeymap(DEFAULT_KEYMAP, overrides, platform));
  return { keymap, calls, registry };
}
const field = { tagName: "INPUT", type: "text" };

describe("text fields", () => {
  test("inputs that take typing, textareas, selects and editable content count", () => {
    assert.equal(isTextField({ tagName: "INPUT", type: "text" }), true);
    assert.equal(isTextField({ tagName: "INPUT", type: "number" }), true);
    assert.equal(isTextField({ tagName: "INPUT" }), true);
    assert.equal(isTextField({ tagName: "TEXTAREA" }), true);
    assert.equal(isTextField({ tagName: "SELECT" }), true);
    assert.equal(isTextField({ tagName: "DIV", isContentEditable: true }), true);
    assert.equal(isTextField({ tagName: "INPUT", type: "range" }), false);
    assert.equal(isTextField({ tagName: "INPUT", type: "checkbox" }), false);
    assert.equal(isTextField({ tagName: "BUTTON" }), false);
    assert.equal(isTextField(null), false);
  });

  test("no binding fires while typing, except those marked text-field", () => {
    for (const target of [
      field,
      { tagName: "TEXTAREA" },
      { tagName: "SELECT" },
      { tagName: "DIV", isContentEditable: true },
    ]) {
      const { keymap, calls } = setup();
      for (const [key, code, extra] of [
        [" ", "Space", {}],
        ["z", "KeyZ", {}],
        ["=", "Equal", {}],
        ["Backspace", "Backspace", {}],
        ["b", "KeyB", {}],
        ["z", "KeyZ", { ctrlKey: true }],
        ["?", "Slash", { shiftKey: true }],
      ]) {
        const event = press({ key, code, target, ...extra });
        assert.equal(keymap.handle(event), false, `${key} in ${target.tagName}`);
        assert.equal(event.prevented, false);
      }
      assert.deepEqual(calls, []);
    }
  });

  test("Esc, F6 and Mod+K act in a text field", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "Escape", code: "Escape", target: field }));
    keymap.handle(press({ key: "F6", code: "F6", target: field }));
    keymap.handle(press({ key: "k", code: "KeyK", ctrlKey: true, target: field }));
    assert.deepEqual(calls, [["nav.home"], ["panel.next", 1], ["palette.open"]]);
  });
});

describe("the core keys", () => {
  test("Space plays/stops, on any element except a text field", () => {
    for (const tag of [
      { tagName: "DIV" },
      { tagName: "BUTTON" },
      { tagName: "INPUT", type: "range" },
    ]) {
      const { keymap, calls } = setup();
      const event = press({ code: "Space", key: " ", target: tag });
      assert.equal(keymap.handle(event), true);
      assert.equal(event.prevented, true);
      assert.deepEqual(calls, [["transport.play"]]);
    }
  });

  test("Space plays in every focus context", () => {
    for (const context of ["timeline", "transcript", "side"]) {
      const { keymap, calls } = setup({ context });
      keymap.handle(press({ code: "Space", key: " " }));
      assert.deepEqual(calls, [["transport.play"]], context);
    }
  });

  test("a held Space does not flip playback back and forth", () => {
    const { keymap, calls } = setup();
    const event = press({ code: "Space", repeat: true });
    assert.equal(keymap.handle(event), true);
    assert.equal(event.prevented, true);
    assert.deepEqual(calls, []);
  });

  test("Z, Shift+Z and Alt+Z (by key position, so a Mac's Option does not change them)", () => {
    const { keymap, calls } = setup({ platform: "mac" });
    keymap.handle(press({ key: "z", code: "KeyZ" }));
    keymap.handle(press({ key: "Z", code: "KeyZ", shiftKey: true }));
    keymap.handle(press({ key: "Ω", code: "KeyZ", altKey: true }));
    keymap.handle(press({ key: "Ω", code: "KeyZ", altKey: true, shiftKey: true }));
    assert.deepEqual(calls, [["view.toggle"], ["view.fit"], ["view.back"], ["view.forward"]]);
  });

  test("= and - zoom, on a US layout and on a Finnish one, and a held key repeats", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "=", code: "Equal" }));
    keymap.handle(press({ key: "-", code: "Minus" }));
    keymap.handle(press({ key: "+", code: "Minus" })); // Finnish: + is unshifted
    keymap.handle(press({ key: "-", code: "Slash" })); // Finnish: - is on the slash key
    keymap.handle(press({ key: "+", code: "Equal", shiftKey: true })); // US Shift+=: not zoom
    keymap.handle(press({ key: "=", code: "Equal", repeat: true }));
    assert.deepEqual(calls, [
      ["view.zoom_in", 1],
      ["view.zoom_out", -1],
      ["view.zoom_in", 1],
      ["view.zoom_out", -1],
      ["view.zoom_in", 1],
    ]);
  });

  test("F6 and Shift+F6 cycle the panels", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "F6", code: "F6" }));
    keymap.handle(press({ key: "F6", code: "F6", shiftKey: true }));
    assert.deepEqual(calls, [
      ["panel.next", 1],
      ["panel.previous", -1],
    ]);
  });

  test("Mod is Cmd on a Mac and Ctrl elsewhere; the other one does nothing", () => {
    const mac = setup({ platform: "mac" });
    mac.keymap.handle(press({ key: "z", code: "KeyZ", ctrlKey: true }));
    mac.keymap.handle(press({ key: "z", code: "KeyZ", metaKey: true }));
    assert.deepEqual(mac.calls, [["edit.undo"]]);
    const other = setup({ platform: "other" });
    other.keymap.handle(press({ key: "z", code: "KeyZ", metaKey: true }));
    other.keymap.handle(press({ key: "z", code: "KeyZ", ctrlKey: true }));
    assert.deepEqual(other.calls, [["edit.undo"]]);
  });

  test("Z with Ctrl or Cmd is undo, not the view toggle", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "z", code: "KeyZ", ctrlKey: true }));
    assert.deepEqual(calls, [["edit.undo"]]);
  });

  test("a context binding fires only in its own panel", () => {
    const timeline = setup({ context: "timeline" });
    timeline.keymap.handle(press({ key: "b", code: "KeyB" }));
    assert.deepEqual(timeline.calls, [["edit.split"]]);
    const side = setup({ context: "side" });
    assert.equal(side.keymap.handle(press({ key: "b", code: "KeyB" })), false);
    assert.deepEqual(side.calls, []);
    const transcript = setup({ context: "transcript" });
    transcript.keymap.handle(press({ key: "Backspace", code: "Backspace" }));
    assert.deepEqual(transcript.calls, [["transcript.delete_words"]]);
    const tl = setup({ context: "timeline" });
    tl.keymap.handle(press({ key: "Backspace", code: "Backspace" }));
    assert.deepEqual(tl.calls, [["edit.delete"]]);
  });

  test("planned commands do nothing and leave the key to the browser", () => {
    const { keymap, calls, registry } = setup();
    registry.planned("edit.split");
    const event = press({ key: "b", code: "KeyB" });
    assert.equal(keymap.handle(event), false);
    assert.equal(event.prevented, false);
    assert.deepEqual(calls, []);
    assert.equal(registry.status("edit.split"), "planned");
  });

  test("WP5 can add ad hoc bindings, and the first match wins", () => {
    const { keymap, calls } = setup();
    keymap.bind({ code: "KeyP", run: () => calls.push(["extra"]) });
    keymap.handle(press({ key: "p", code: "KeyP" }));
    assert.deepEqual(calls, [["extra"]]);
  });
});

describe("user overrides in the dispatcher", () => {
  test("a remapped key fires the command and the old key goes quiet", () => {
    const { keymap, calls } = setup({ overrides: { "edit.split": "Mod+B" } });
    assert.equal(keymap.handle(press({ key: "b", code: "KeyB" })), false);
    keymap.handle(press({ key: "b", code: "KeyB", ctrlKey: true }));
    assert.deepEqual(calls, [["edit.split"]]);
  });

  test("an unbound command (null) has no key", () => {
    const { keymap, calls } = setup({ overrides: { "view.toggle": null } });
    assert.equal(keymap.handle(press({ key: "z", code: "KeyZ" })), false);
    assert.deepEqual(calls, []);
  });
});

describe("physical keys on a Finnish layout", () => {
  test("[ and ] are the keys at BracketLeft/BracketRight, whatever they print", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "å", code: "BracketLeft" })); // Finnish: Å sits there
    keymap.handle(press({ key: "¨", code: "BracketRight" }));
    keymap.handle(press({ key: "[", code: "BracketLeft" })); // US
    assert.deepEqual(calls, [["candidate.previous"], ["candidate.next"], ["candidate.previous"]]);
  });

  test("[ typed with AltGr (Finnish Windows/Linux) or Option (Finnish Mac) also works", () => {
    const win = setup();
    win.keymap.handle(press({ key: "[", code: "Digit8", ...altGr }));
    win.keymap.handle(press({ key: "]", code: "Digit9", ...altGr }));
    assert.deepEqual(win.calls, [["candidate.previous"], ["candidate.next"]]);
    const mac = setup({ platform: "mac" });
    mac.keymap.handle(press({ key: "[", code: "Digit8", altKey: true }));
    assert.deepEqual(mac.calls, [["candidate.previous"]]);
  });

  test("letters follow the key position on other layouts", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "ö", code: "KeyZ" })); // Dvorak-like: position wins
    assert.deepEqual(calls, [["view.toggle"]]);
  });

  test("? is accepted wherever it is typed (Shift+Plus on a Finnish board)", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "?", code: "Minus", shiftKey: true }));
    keymap.handle(press({ key: "?", code: "Slash", shiftKey: true }));
    assert.deepEqual(calls, [["help.keys"], ["help.keys"]]);
  });
});

describe("AltGr", () => {
  test("AltGr is not Ctrl+Alt: AltGr+Q (@) does not fire Alt+Mod+Q style bindings", () => {
    const { keymap, calls } = setup();
    // Alt+Mod+M is "mute clips". AltGr+M on Windows reports ctrl+alt.
    assert.equal(keymap.handle(press({ key: "µ", code: "KeyM", ...altGr })), false);
    keymap.handle(press({ key: "m", code: "KeyM", ctrlKey: true, altKey: true }));
    assert.deepEqual(calls, [["clip.mute"]]);
  });

  test("AltGr is not Ctrl: AltGr+Z does not undo", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "z", code: "KeyZ", ...altGr }));
    assert.deepEqual(calls, []);
  });
});

describe("keyboard focus", () => {
  test("the order is timeline, transcript, inspector, candidates, clipboard, history", () => {
    assert.deepEqual(PANELS, [
      "timeline",
      "transcript",
      "inspector",
      "candidates",
      "clipboard",
      "history",
    ]);
  });

  test("F6 steps forward and wraps; Shift+F6 steps back and wraps", () => {
    assert.equal(nextPanel("timeline", 1), "transcript");
    assert.equal(nextPanel("history", 1), "timeline");
    assert.equal(nextPanel("timeline", -1), "history");
    assert.equal(nextPanel("inspector", -1), "transcript");
  });

  test("an unknown or missing focus starts from the timeline", () => {
    assert.equal(nextPanel(null, 1), "transcript");
    assert.equal(nextPanel("nowhere", -1), "history");
  });
});
