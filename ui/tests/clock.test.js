import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createClock } from "../clock.js";

class FakeElement {
  listeners = new Map();
  attributes = {};
  children = [];
  textContent = "0:00:00";

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

function harness({ withSpot = false } = {}) {
  const previousDocument = globalThis.document;
  const jumps = [];
  const spots = [];
  const notices = [];
  let state = { project: {}, playhead: 0 };
  const el = new FakeElement();
  globalThis.document = { createElement: () => new FakeElement() };
  const clock = createClock({
    el,
    getState: () => state,
    rate: () => 48_000,
    limit: () => 20 * 3600 * 48_000,
    format: (frame) => {
      const total = Math.floor(frame / 48_000);
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor((total % 3600) / 60);
      const seconds = total % 60;
      return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    },
    jump: (frame) => {
      jumps.push(frame);
      state = { ...state, playhead: frame };
    },
    ...(withSpot ? { spot: (frame) => spots.push(frame) } : {}),
    notify: (...args) => notices.push(args),
    t: (key) => key,
  });

  return {
    clock,
    el,
    jumps,
    spots,
    notices,
    openByDoubleClick() {
      el.fire("dblclick", { preventDefault() {} });
      return el.children.at(-1);
    },
    restoreDocument() {
      if (previousDocument === undefined) delete globalThis.document;
      else globalThis.document = previousDocument;
    },
  };
}

function key(input, value) {
  let prevented = false;
  input.fire("keydown", {
    key: value,
    metaKey: false,
    ctrlKey: false,
    altKey: false,
    stopPropagation() {},
    preventDefault() {
      prevented = true;
    },
  });
  return prevented;
}

describe("playhead clock time entry", () => {
  test("Enter jumps to a pasted time and displays overflowed minutes as hours", () => {
    const h = harness();
    try {
      const input = h.openByDoubleClick();
      input.fire("paste", {
        preventDefault() {},
        clipboardData: { getData: () => "100:00" },
      });

      assert.equal(key(input, "Enter"), true);
      assert.deepEqual(h.jumps, [6000 * 48_000]);
      assert.equal(h.el.textContent, "1:40:00");
      assert.equal(h.clock.editing(), false);
    } finally {
      h.restoreDocument();
    }
  });

  test("Enter jumps to a typed timecode with hours and milliseconds", () => {
    const h = harness();
    try {
      const input = h.openByDoubleClick();
      input.fire("paste", {
        preventDefault() {},
        clipboardData: { getData: () => "1:02:03.500" },
      });

      key(input, "Enter");
      assert.deepEqual(h.jumps, [Math.round(3723.5 * 48_000)]);
      assert.equal(h.el.textContent, "1:02:03");
    } finally {
      h.restoreDocument();
    }
  });

  test("Enter sends the resolved time to spot placement", () => {
    const h = harness({ withSpot: true });
    try {
      const input = h.openByDoubleClick();
      input.fire("paste", {
        preventDefault() {},
        clipboardData: { getData: () => "1:02:03.500" },
      });

      key(input, "Enter");
      assert.deepEqual(h.spots, [Math.round(3723.5 * 48_000)]);
      assert.deepEqual(h.jumps, []);
    } finally {
      h.restoreDocument();
    }
  });
});
