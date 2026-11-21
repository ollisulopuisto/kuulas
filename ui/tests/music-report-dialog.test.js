// File > Statistics… drawn into a tiny stand-in for the DOM: a row the server sends with a
// third element (the Size group's one-line hint) shows that hint under its label.
import assert from "node:assert/strict";
import { test } from "node:test";

class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.listeners = {};
    this.className = "";
    this.textContent = "";
    this.open = false;
    this.classList = {
      add: (name) => {
        this.className = `${this.className} ${name}`.trim();
      },
    };
  }
  append(...nodes) {
    this.children.push(...nodes);
  }
  replaceChildren(...nodes) {
    this.children = nodes;
    this.textContent = "";
  }
  setAttribute() {}
  addEventListener(type, fn) {
    this.listeners[type] = [...(this.listeners[type] ?? []), fn];
  }
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
  all() {
    return this.children.flatMap((c) => (c instanceof FakeNode ? [c, ...c.all()] : []));
  }
}

globalThis.document = {
  createElement: (tag) => new FakeNode(tag),
  body: new FakeNode("body"),
};

const { createMusicReportDialog } = await import("../music-report-dialog.js");

test("solo notice survives an empty report and copy, and clears on reload", async () => {
  const notice = "Solo is active: some music is excluded from this report.";
  let answer = { rows: [], warnings: [notice] };
  let copied;
  const dialog = createMusicReportDialog({
    api: { musicReport: async () => answer },
    t: (key) => key,
    getProject: () => ({}),
    copyText: (text) => {
      copied = text;
    },
    saveFile: () => {},
  });
  await dialog.open();
  const node = dialog.element.children[2];
  assert.equal(node.textContent, notice);
  assert.equal(node.hidden, false);
  const copy = dialog.element.all().find((n) => n.dataset.icon === "copy");
  assert.equal(copy.disabled, false);
  copy.listeners.click[0]();
  assert.equal(copied.split("\n")[0], notice);
  answer = { rows: [] };
  await dialog.open();
  assert.equal(node.hidden, true);
  assert.equal(node.textContent, "");
  assert.equal(copy.disabled, true);
});
