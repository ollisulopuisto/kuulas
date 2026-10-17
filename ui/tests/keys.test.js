import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { nextPanel, PANELS } from "../focus.js";
import { coreBindings, createKeymap, isTextField } from "../keys.js";

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
  ...over,
});

function setup() {
  const calls = [];
  const actions = new Proxy(
    {},
    {
      get:
        (_t, name) =>
        (...args) =>
          calls.push([name, ...args]),
    },
  );
  const keymap = createKeymap();
  for (const binding of coreBindings(actions)) keymap.bind(binding);
  return { keymap, calls };
}

describe("text fields", () => {
  test("inputs that take typing, textareas and editable content count", () => {
    assert.equal(isTextField({ tagName: "INPUT", type: "text" }), true);
    assert.equal(isTextField({ tagName: "INPUT", type: "number" }), true);
    assert.equal(isTextField({ tagName: "INPUT" }), true);
    assert.equal(isTextField({ tagName: "TEXTAREA" }), true);
    assert.equal(isTextField({ tagName: "DIV", isContentEditable: true }), true);
    assert.equal(isTextField({ tagName: "INPUT", type: "range" }), false);
    assert.equal(isTextField({ tagName: "INPUT", type: "checkbox" }), false);
    assert.equal(isTextField({ tagName: "BUTTON" }), false);
    assert.equal(isTextField(null), false);
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
      assert.deepEqual(calls, [["togglePlay"]]);
    }
    const { keymap, calls } = setup();
    const inField = press({ code: "Space", key: " ", target: { tagName: "INPUT", type: "text" } });
    assert.equal(keymap.handle(inField), false);
    assert.equal(inField.prevented, false);
    assert.deepEqual(calls, []);
  });

  test("a held Space does not flip playback back and forth", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ code: "Space", repeat: true }));
    assert.deepEqual(calls, []);
  });

  test("Esc returns home, also from a text field", () => {
    const { keymap, calls } = setup();
    keymap.handle(
      press({ key: "Escape", code: "Escape", target: { tagName: "INPUT", type: "text" } }),
    );
    assert.deepEqual(calls, [["goHome"]]);
  });

  test("F6 and Shift+F6 cycle the panels, also from a text field", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "F6", code: "F6", target: { tagName: "INPUT", type: "text" } }));
    keymap.handle(press({ key: "F6", code: "F6", shiftKey: true }));
    assert.deepEqual(calls, [
      ["cyclePanel", 1],
      ["cyclePanel", -1],
    ]);
  });

  test("Z, Shift+Z and Alt+Z (by key position, so a Mac's Option does not change them)", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "z", code: "KeyZ" }));
    keymap.handle(press({ key: "Z", code: "KeyZ", shiftKey: true }));
    keymap.handle(press({ key: "Ω", code: "KeyZ", altKey: true }));
    keymap.handle(press({ key: "Ω", code: "KeyZ", altKey: true, shiftKey: true }));
    assert.deepEqual(calls, [["toggleView"], ["fitView"], ["viewBack"], ["viewForward"]]);
  });

  test("= and - zoom, on a US layout and on a Finnish one", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "=", code: "Equal" }));
    keymap.handle(press({ key: "-", code: "Minus" }));
    keymap.handle(press({ key: "+", code: "Minus" })); // Finnish: + is unshifted
    keymap.handle(press({ key: "-", code: "Slash" })); // Finnish: - is on the slash key
    assert.deepEqual(calls, [
      ["zoomStep", 1],
      ["zoomStep", -1],
      ["zoomStep", 1],
      ["zoomStep", -1],
    ]);
  });

  test("typing in a text field is never taken by Z, = or -", () => {
    const { keymap, calls } = setup();
    const target = { tagName: "TEXTAREA" };
    for (const [key, code] of [
      ["z", "KeyZ"],
      ["=", "Equal"],
      ["-", "Minus"],
    ]) {
      assert.equal(keymap.handle(press({ key, code, target })), false);
    }
    assert.deepEqual(calls, []);
  });

  test("keys with Ctrl or Cmd are left to the browser and to WP5", () => {
    const { keymap, calls } = setup();
    keymap.handle(press({ key: "z", code: "KeyZ", metaKey: true }));
    keymap.handle(press({ key: "z", code: "KeyZ", ctrlKey: true }));
    keymap.handle(press({ code: "Space", metaKey: true }));
    assert.deepEqual(calls, []);
  });

  test("WP5 can add bindings to the same map, and the first match wins", () => {
    const { keymap, calls } = setup();
    keymap.bind({ code: "KeyB", run: () => calls.push(["split"]) });
    keymap.handle(press({ key: "b", code: "KeyB" }));
    assert.deepEqual(calls, [["split"]]);
  });
});

describe("keyboard focus", () => {
  test("the order is timeline, transcript, inspector, history", () => {
    assert.deepEqual(PANELS, ["timeline", "transcript", "inspector", "history"]);
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
