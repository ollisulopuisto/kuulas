import assert from "node:assert/strict";
import { test } from "node:test";

class FakeNode {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
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
    this.classList = { add() {}, toggle() {} };
  }

  append(...nodes) {
    this.children.push(...nodes);
  }

  get firstChild() {
    return this.children[0] ?? null;
  }

  get lastChild() {
    return this.children.at(-1) ?? null;
  }

  before() {}

  addEventListener(type, callback) {
    this.listeners[type] = [...(this.listeners[type] ?? []), callback];
  }

  appendChild(node) {
    this.append(node);
  }

  createTextNode(text) {
    return { textContent: text };
  }

  focus() {}

  matches(selector) {
    return selector.split(",").some((tag) => this.tagName === tag.trim().toUpperCase());
  }

  querySelector(selector) {
    return (
      this.all().find((node) =>
        selector.startsWith(".")
          ? node.className.split(/\s+/).includes(selector.slice(1))
          : node.matches(selector),
      ) ?? null
    );
  }

  querySelectorAll() {
    return [];
  }

  replaceChildren(...nodes) {
    this.children = [...nodes];
  }

  setAttribute(name, value) {
    this.attrs[name] = value;
  }

  removeAttribute(name) {
    delete this.attrs[name];
  }

  showModal() {
    this.open = true;
  }

  close() {
    this.open = false;
    for (const listener of this.listeners.close ?? []) listener();
  }

  all() {
    return this.children.flatMap((child) =>
      child instanceof FakeNode ? [child, ...child.all()] : [],
    );
  }
}

globalThis.document = {
  body: new FakeNode("body"),
  createElement: (tag) => new FakeNode(tag),
  createTextNode: (text) => ({ textContent: text }),
};
globalThis.localStorage = { getItem: () => null, setItem: () => {} };

const { createAutomixDialog } = await import("../automix-dialog.js");

test("opens the settings dialog before waiting for the Automixer settings API", async () => {
  let resolveSettings;
  const settings = new Promise((resolve) => {
    resolveSettings = resolve;
  });
  const dialog = createAutomixDialog({
    api: { automixerSettings: () => settings },
    t: (key) => key,
    onStart: () => {},
  });

  const opening = dialog.open();
  assert.equal(dialog.element.open, true);
  dialog.element.close();
  resolveSettings({});
  await opening;
});
