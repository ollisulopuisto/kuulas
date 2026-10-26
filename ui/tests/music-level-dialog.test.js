import assert from "node:assert/strict";
import { test } from "node:test";

class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.listeners = {};
    this.attrs = {};
    this.dataset = {};
    this.className = "";
    this.value = "";
    this.type = "";
    this.hidden = false;
    this.disabled = false;
    this.open = false;
    this.classList = { add: () => {} };
  }

  append(...nodes) {
    this.children.push(...nodes);
  }

  replaceChildren(...nodes) {
    this.children = nodes;
  }

  setAttribute(name, value) {
    this.attrs[name] = value;
  }

  addEventListener(type, fn) {
    this.listeners[type] = [...(this.listeners[type] ?? []), fn];
  }

  querySelectorAll() {
    return [];
  }

  showModal() {
    this.open = true;
  }

  close() {
    this.open = false;
  }

  all() {
    return this.children.flatMap((child) =>
      child instanceof FakeNode ? [child, ...child.all()] : [],
    );
  }
}

globalThis.document = {
  createElement: (tag) => new FakeNode(tag),
  body: new FakeNode("body"),
};

const { createMusicLevelDialog } = await import("../music-level-dialog.js");

test("the offset slider and number field share the full signed range", () => {
  const dialog = createMusicLevelDialog({
    api: {},
    t: (key) => key,
    fmt: (value) => String(value),
    getOffset: () => -10,
    onApply: () => {},
    onRemember: () => {},
  });
  const controls = dialog.element.all().filter((node) => node.tagName === "input");
  const slider = controls.find((node) => node.type === "range");
  const field = controls.find((node) => node.type === "text");

  assert.ok(slider);
  assert.ok(field);
  assert.deepEqual([slider.min, slider.max, slider.step], ["-30", "1", "0.1"]);
  slider.value = "1";
  slider.listeners.input[0]();
  assert.equal(field.value, "1");
  field.value = "-5.5";
  field.listeners.input[0]();
  assert.equal(slider.value, "-5.5");
});
