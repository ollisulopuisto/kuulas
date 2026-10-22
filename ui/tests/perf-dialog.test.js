// Help > Record a performance report…: reopening the dialog while a recording runs must not
// start a second polling chain. Before, each reopen added one more GET /api/profile every
// 500 ms until the recording ended.
import assert from "node:assert/strict";
import { mock, test } from "node:test";

class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.className = "";
    this.textContent = "";
    this.open = false;
    this.classList = { add: () => {} };
  }
  append(...nodes) {
    this.children.push(...nodes);
  }
  setAttribute() {}
  addEventListener() {}
  querySelectorAll() {
    return [];
  }
  querySelector() {
    return null;
  }
  showModal() {
    this.open = true;
  }
  close() {
    this.open = false;
  }
  focus() {}
}

globalThis.document = {
  createElement: (tag) => new FakeNode(tag),
  body: new FakeNode("body"),
};

const { createPerfDialog } = await import("../perf-dialog.js");

test("opening the dialog again while recording keeps one poll going", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    let calls = 0;
    const api = {
      getProfile: async () => {
        calls += 1;
        return { state: "running", seconds: 60, elapsed: 1 };
      },
    };
    const dialog = createPerfDialog({ api, t: (key) => key, notify: () => {} });
    await dialog.open();
    for (let i = 0; i < 5; i += 1) await dialog.open(); // closed and opened again
    const settle = async () => {
      for (let i = 0; i < 5; i += 1) await Promise.resolve();
    };
    await settle();
    const before = calls;
    for (let i = 0; i < 4; i += 1) {
      mock.timers.tick(500);
      await settle();
    }
    assert.equal(calls - before, 4, `${calls - before} polls in 4 ticks`);
  } finally {
    mock.timers.reset();
  }
});
