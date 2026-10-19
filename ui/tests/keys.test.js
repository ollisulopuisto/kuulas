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

describe("the shuttle keys", () => {
  test("K stops the shuttle in every context, the Candidates tab included", () => {
    for (const context of ["timeline", "transcript", "side", "candidates"]) {
      const { keymap, calls } = setup({ context });
      assert.equal(keymap.handle(press({ code: "KeyK", key: "k" })), true);
      assert.deepEqual(calls, [["transport.shuttle_stop"]], context);
    }
  });

  test("in the Candidates tab Enter keeps and Backspace deletes the candidate", () => {
    const keep = setup({ context: "candidates" });
    keep.keymap.handle(press({ code: "Enter", key: "Enter" }));
    assert.deepEqual(keep.calls, [["candidate.reject"]]);
    const del = setup({ context: "candidates" });
    del.keymap.handle(press({ code: "Backspace", key: "Backspace" }));
    assert.deepEqual(del.calls, [["candidate.apply"]]);
  });

  test("J and L shuttle in every context, and not while typing", () => {
    for (const context of ["timeline", "transcript", "side", "candidates"]) {
      const { keymap, calls } = setup({ context });
      keymap.handle(press({ code: "KeyJ", key: "j" }));
      keymap.handle(press({ code: "KeyL", key: "l" }));
      assert.deepEqual(calls, [["transport.shuttle_back"], ["transport.shuttle_forward"]], context);
    }
    const { keymap, calls } = setup();
    keymap.handle(press({ code: "KeyL", key: "l", target: field }));
    assert.deepEqual(calls, []);
  });

  test("the keys can be remapped", () => {
    const { keymap, calls } = setup({ overrides: { "transport.shuttle_forward": "Alt+L" } });
    keymap.handle(press({ code: "KeyL", key: "l" }));
    keymap.handle(press({ code: "KeyL", key: "l", altKey: true }));
    assert.deepEqual(calls, [["transport.shuttle_forward"]]);
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

  test("Z toggles, 0 shows all, and F fits the selection", () => {
    const { keymap, calls } = setup({ platform: "mac" });
    keymap.handle(press({ key: "z", code: "KeyZ" }));
    keymap.handle(press({ key: "0", code: "Digit0" }));
    keymap.handle(press({ key: "f", code: "KeyF" }));
    assert.deepEqual(calls, [["view.toggle"], ["view.fit"], ["view.fit_selection"]]);
  });

  test("layout-free keys: Alt+Down/Up step candidates, Cmd+Alt+Shift+Left/Right step the views", () => {
    const { keymap, calls } = setup({ platform: "mac" });
    keymap.handle(press({ key: "ArrowDown", code: "ArrowDown", altKey: true }));
    keymap.handle(press({ key: "ArrowUp", code: "ArrowUp", altKey: true }));
    const chord = { metaKey: true, altKey: true, shiftKey: true };
    keymap.handle(press({ key: "ArrowLeft", code: "ArrowLeft", ...chord }));
    keymap.handle(press({ key: "ArrowRight", code: "ArrowRight", ...chord }));
    assert.deepEqual(calls, [
      ["candidate.next"],
      ["candidate.previous"],
      ["view.back"],
      ["view.forward"],
    ]);
  });

  test("Alt+. speeds fast listening up by code (Option+. types another character), Shift+J/L are slow listening", () => {
    const { keymap, calls } = setup({ platform: "mac" });
    keymap.handle(press({ key: "≥", code: "Period", altKey: true })); // Mac Option+.
    keymap.handle(press({ key: ".", code: "Period", altKey: true })); // Windows/Linux
    keymap.handle(press({ key: ".", code: "Period" })); // plain: the toggle
    keymap.handle(press({ key: ",", code: "Comma" }));
    keymap.handle(press({ key: "J", code: "KeyJ", shiftKey: true }));
    keymap.handle(press({ key: "L", code: "KeyL", shiftKey: true }));
    keymap.handle(press({ key: "K", code: "KeyK", shiftKey: true }));
    assert.deepEqual(calls, [
      ["transport.speed_up"],
      ["transport.speed_up"],
      ["transport.speed"],
      ["transport.speed_down"],
      ["transport.slow_back"],
      ["transport.slow_forward"],
    ]);
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
  test("no default key is on a bracket key: [ ] Alt+[ Alt+] Å ¨ and Option+8/9 do nothing", () => {
    for (const platform of ["mac", "other"]) {
      const { keymap, calls } = setup({ platform });
      for (const altKey of [false, true]) {
        keymap.handle(press({ key: "å", code: "BracketLeft", altKey }));
        keymap.handle(press({ key: "¨", code: "BracketRight", altKey }));
        keymap.handle(press({ key: "[", code: "BracketLeft", altKey }));
        keymap.handle(press({ key: "]", code: "BracketRight", altKey }));
      }
      keymap.handle(press({ key: "[", code: "Digit8", altKey: true }));
      assert.deepEqual(calls, [], platform);
    }
  });

  test("a user's own [ and ] overrides still work: by position, and typed with AltGr/Option", () => {
    const overrides = { "candidate.previous": "[", "candidate.next": "]" };
    const one = setup({ overrides });
    one.keymap.handle(press({ key: "å", code: "BracketLeft" })); // Finnish: Å sits there
    one.keymap.handle(press({ key: "¨", code: "BracketRight" }));
    one.keymap.handle(press({ key: "[", code: "BracketLeft" })); // US
    assert.deepEqual(one.calls, [
      ["candidate.previous"],
      ["candidate.next"],
      ["candidate.previous"],
    ]);
    const win = setup({ overrides });
    win.keymap.handle(press({ key: "[", code: "Digit8", ...altGr }));
    win.keymap.handle(press({ key: "]", code: "Digit9", ...altGr }));
    assert.deepEqual(win.calls, [["candidate.previous"], ["candidate.next"]]);
    const mac = setup({ platform: "mac", overrides });
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
  test("the order is timeline, transcript, inspector, candidates, clipboard, markers, history", () => {
    assert.deepEqual(PANELS, [
      "timeline",
      "transcript",
      "inspector",
      "candidates",
      "clipboard",
      "markers",
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

describe("Tab in the timeline context", () => {
  const tab = (over = {}) => press({ key: "Tab", code: "Tab", ...over });
  test("steps whatever non-text control has the focus: canvas, a header button, the body", () => {
    for (const target of [{ tagName: "CANVAS" }, { tagName: "BUTTON" }, { tagName: "BODY" }]) {
      const { keymap, calls } = setup({ context: "timeline" });
      const event = tab({ target });
      assert.equal(keymap.handle(event), true);
      assert.equal(event.prevented, true);
      assert.deepEqual(calls, [["nav.next_stop"]]);
    }
  });
  test("Shift+Tab steps back", () => {
    const { keymap, calls } = setup({ context: "timeline" });
    keymap.handle(tab({ shiftKey: true, target: { tagName: "BUTTON" } }));
    assert.deepEqual(calls, [["nav.prev_stop"]]);
  });
  test("keeps the browser's focus move in text fields and in the side panels", () => {
    const typing = setup({ context: "timeline" });
    assert.equal(typing.keymap.handle(tab({ target: field })), false);
    const side = setup({ context: "side" });
    assert.equal(side.keymap.handle(tab({ target: { tagName: "BUTTON" } })), false);
    assert.deepEqual([...typing.calls, ...side.calls], []);
  });
});
