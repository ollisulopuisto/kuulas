import assert from "node:assert/strict";
import { test } from "node:test";
import { createPartVersionsDialog } from "../part-versions-dialog.js";

class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.events = {};
    this.open = false;
  }
  append(...nodes) {
    this.children.push(...nodes);
  }
  replaceChildren(...nodes) {
    this.children = nodes;
  }
  setAttribute() {}
  querySelectorAll() {
    return [];
  }
  addEventListener(name, run) {
    this.events[name] ??= [];
    this.events[name].push(run);
  }
  async fire(name) {
    for (const run of this.events[name] ?? []) await run();
  }
  showModal() {
    this.open = true;
  }
  close() {
    this.open = false;
    void this.fire("close");
  }
  getContext() {
    return { beginPath() {}, moveTo() {}, lineTo() {}, stroke() {} };
  }
  all() {
    return this.children.flatMap((child) => [child, ...child.all()]);
  }
}

test("chooser pages rows, previews without applying, and explicitly restores with its head", async () => {
  const original = globalThis.document;
  globalThis.document = { createElement: (tag) => new Element(tag), body: new Element("body") };
  try {
    const calls = [];
    const versions = Array.from({ length: 10 }, (_, i) => ({
      node: `node-${i}`,
      head: "head",
      names: ["Voice"],
      first_created: "2026-10-28",
      created: "2026-10-29",
      clips: [],
      current: i === 0,
    }));
    const chooser = createPartVersionsDialog({
      t: (key, args) => (key === "ui.part_versions.row" ? JSON.stringify(args) : key),
      api: {
        partVersions: async () => ({ versions }),
        previewPartVersion: async (body) => calls.push(["preview", body]),
        restorePartVersion: async (body) => {
          calls.push(["restore", body]);
          return { state: 1 };
        },
        stopClipboardPreview: async () => calls.push(["stop"]),
      },
      apply: (state) => calls.push(["apply", state]),
      notice() {},
    });
    await chooser.open({ track_id: "t", start: 10, end: 20 }, 48000);
    const dialog = document.body.children[0];
    const sections = () => dialog.all().filter((node) => node.tagName === "section");
    assert.equal(sections().length, 8);
    assert.match(sections()[0].children[0].textContent, /2026-10-28.*2026-10-29/);
    assert.equal(sections()[0].children.at(-1).disabled, true);
    const more = dialog.children.find((node) => node.textContent === "ui.part_versions.more");
    await more.fire("click");
    assert.equal(sections().length, 10);
    assert.equal(more.hidden, true);
    const restore = sections()[1].children.at(-1);
    await restore.fire("click");
    assert.equal(calls.find(([kind]) => kind === "restore")[1].expected_head, "head");
    assert.equal(calls.find(([kind]) => kind === "restore")[1].node, "node-1");
    assert.equal(calls.filter(([kind]) => kind === "apply").length, 1);
    assert.equal(dialog.open, false);
  } finally {
    globalThis.document = original;
  }
});

test("closing while history is loading drops the late reply", async () => {
  const original = globalThis.document;
  globalThis.document = { createElement: (tag) => new Element(tag), body: new Element("body") };
  try {
    let answer;
    const waiting = new Promise((resolve) => {
      answer = resolve;
    });
    const chooser = createPartVersionsDialog({
      t: (key) => key,
      api: { partVersions: () => waiting, stopClipboardPreview: async () => {} },
      apply() {
        assert.fail("must not apply");
      },
      notice() {},
    });
    const opening = chooser.open({ track_id: "t", start: 0, end: 10 }, 48000);
    const dialog = document.body.children[0];
    dialog.close();
    answer({ versions: [] });
    await opening;
    assert.equal(dialog.open, false);
    assert.equal(dialog.children[2].children.length, 0);
  } finally {
    globalThis.document = original;
  }
});
