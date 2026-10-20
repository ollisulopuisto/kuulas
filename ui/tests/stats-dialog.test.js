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

const { createStatsDialog } = await import("../stats-dialog.js");

test("a row's hint is shown under its label; rows without one have none", async () => {
  const groups = [
    { title: "Work", rows: [["Steps", "3"]] },
    {
      title: "Size",
      rows: [["Backups", "12.0 MB (4)", "Copies of the history, kept for safety."]],
    },
  ];
  const dialog = createStatsDialog({
    api: { getStats: async () => ({ text: "", groups }) },
    t: (key) => key,
    copyText: () => {},
    saveJson: () => {},
  });
  await dialog.open();
  const nodes = dialog.element.all();
  const hints = nodes.filter((n) => n.className.split(" ").includes("stats-hint"));
  assert.deepEqual(
    hints.map((n) => n.textContent),
    ["Copies of the history, kept for safety."],
  );
  const terms = nodes.filter((n) => n.tagName === "dt");
  assert.deepEqual(
    terms.map((n) => n.textContent),
    ["Steps", "Backups"],
  );
  const values = nodes.filter((n) => n.tagName === "dd").map((n) => n.textContent);
  assert.deepEqual(values, ["3", "12.0 MB (4)"]);
});
