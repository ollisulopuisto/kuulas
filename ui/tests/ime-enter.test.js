// Enter during IME composition (CJK input) is the composition's confirm key,
// not a submit: a keydown-Enter action must check isComposing / keyCode 229,
// the same idiom as ui/dialog-keys.js. modern-web-guidance legacy-scan
// (ime-safe-enter-submit) flagged the handlers listed in GUARDED below.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { bindToggle } from "../ab-value.js";
import { createClock } from "../clock.js";

class FakeElement {
  listeners = new Map();
  attributes = {};
  children = [];
  textContent = "0:00:00";
  classList = { remove() {}, add() {} };

  addEventListener(name, listener) {
    const listeners = this.listeners.get(name) ?? [];
    listeners.push(listener);
    this.listeners.set(name, listeners);
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  append(child) {
    this.children.push(child);
  }

  focus() {}
  select() {}
  setSelectionRange() {}

  fire(name, event = {}) {
    for (const listener of this.listeners.get(name) ?? []) listener(event);
  }
}

const keyEvent = (extra = {}) => ({
  key: "Enter",
  stopPropagation() {},
  preventDefault() {},
  ...extra,
});

describe("ab-value bindToggle", () => {
  test("Shift+Enter toggles; a composing Enter does not", () => {
    const input = new FakeElement();
    const writes = [];
    bindToggle(input, {
      key: "ime-enter-test",
      fallback: 0,
      read: () => -2,
      write: (value) => writes.push(value),
    });
    input.fire("keydown", keyEvent({ shiftKey: true, isComposing: true }));
    input.fire("keydown", keyEvent({ shiftKey: true, keyCode: 229 }));
    assert.deepEqual(writes, []);
    input.fire("keydown", keyEvent({ shiftKey: true }));
    assert.equal(writes.length, 1);
  });
});

describe("playhead clock entry", () => {
  const harness = () => {
    const previousDocument = globalThis.document;
    const jumps = [];
    let state = { project: {}, playhead: 0 };
    const el = new FakeElement();
    globalThis.document = { createElement: () => new FakeElement() };
    const clock = createClock({
      el,
      getState: () => state,
      rate: () => 48_000,
      limit: () => 20 * 3600 * 48_000,
      format: (frame) => String(frame),
      jump: (frame) => {
        jumps.push(frame);
        state = { ...state, playhead: frame };
      },
      notify: () => {},
      t: (key) => key,
    });
    return {
      clock,
      el,
      jumps,
      open() {
        el.fire("dblclick", { preventDefault() {} });
        return el.children.at(-1);
      },
      restore() {
        if (previousDocument === undefined) delete globalThis.document;
        else globalThis.document = previousDocument;
      },
    };
  };

  test("a composing Enter does not jump; the next plain Enter does", () => {
    const h = harness();
    try {
      const input = h.open();
      input.fire("paste", {
        preventDefault() {},
        clipboardData: { getData: () => "1:00" },
      });
      input.fire("keydown", keyEvent({ isComposing: true }));
      assert.deepEqual(h.jumps, []);
      input.fire("keydown", keyEvent({}));
      assert.deepEqual(h.jumps, [60 * 48_000]);
    } finally {
      h.restore();
    }
  });
});

// The flagged handlers (file: keydown-listener line, from the scan report).
// The guard must be right inside the listener, so composing keys return
// before Enter (or Escape) acts.
const GUARDED = {
  "ab-value.js": [75],
  "clipboard-panel.js": [117, 616],
  "clock.js": [77],
  "history-panel.js": [316],
  "inspector-track.js": [89, 233],
  "inspector.js": [194],
  "markers-panel.js": [42],
  "marks-corner.js": [160],
  "timeline.js": [1949],
  "tracks.js": [115, 156, 838],
  "transcript.js": [1139, 1404],
};

describe("every flagged Enter handler guards IME composition", () => {
  for (const [file, lines] of Object.entries(GUARDED)) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8").split("\n");
    for (const line of lines) {
      test(`${file}:${line}`, () => {
        assert.match(source[line - 1], /addEventListener\("keydown"/, "listener moved; re-anchor");
        const head = source.slice(line, line + 3).join("\n");
        assert.match(head, /isComposing/, "no isComposing guard at the top of the handler");
      });
    }
  }
});

// Devin review (PR #216, tracks.js): a handler that previously stopped every
// keydown must keep doing so - the guard goes AFTER stopPropagation, or a
// composing Escape bubbles to dismissFlyoutOnEscape and closes the flyout.
const CONTAINED = {
  "clipboard-panel.js": [117, 616],
  "clock.js": [77],
  "history-panel.js": [316],
  "markers-panel.js": [42],
  "marks-corner.js": [160],
  "timeline.js": [1949],
  "tracks.js": [156],
};

describe("contained handlers keep stopPropagation ahead of the guard", () => {
  for (const [file, lines] of Object.entries(CONTAINED)) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8").split("\n");
    for (const line of lines) {
      test(`${file}:${line}`, () => {
        const head = source.slice(line, line + 5).join("\n");
        const stop = head.indexOf("stopPropagation()");
        const guard = head.indexOf("isComposing");
        assert.notEqual(stop, -1, "no stopPropagation near the listener; re-check containment");
        assert.ok(stop < guard, "stopPropagation must run before the composition guard");
      });
    }
  }
});
