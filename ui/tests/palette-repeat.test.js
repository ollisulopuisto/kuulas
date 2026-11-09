// The Mod+K palette drawn into a small stand-in for the DOM: Enter twice on a repeatable
// command (zoom in) runs it twice and leaves the palette open; a normal command closes it.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createPalette, paletteRows } from "../palette.js";

class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.attrs = {};
    this.listeners = {};
    this.dataset = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
    this.hidden = false;
    this.isConnected = true;
    this.id = "";
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
  focus() {}
  querySelector() {
    return null;
  }
}

function press(node, key) {
  for (const fn of node.listeners.keydown ?? []) {
    fn({ key, preventDefault() {}, stopPropagation() {} });
  }
}

const ENTRIES = [
  { id: "view.zoom_in", labelKey: "cmd.zoom_in", raw: ["Mod+="] },
  { id: "edit.split", labelKey: "cmd.split", raw: ["B"] },
];

function build() {
  globalThis.document = {
    createElement: (tag) => new FakeNode(tag),
    activeElement: null,
    body: new FakeNode("body"),
  };
  const registry = {
    has: () => true,
    can: () => true,
    status: () => "ready",
    hintKey: () => null,
  };
  const ran = [];

  const names = { "cmd.zoom_in": "Zoom in", "cmd.split": "Split" };
  const palette = createPalette({
    t: (key) => key,
    getRows: (query) =>
      paletteRows({
        entries: ENTRIES,
        registry,
        state: {},
        query,
        label: (key) => names[key] ?? key,
        format: (raw) => raw,
        platform: "other",
      }),
    run(id) {
      ran.push(id);
      return true;
    },
  });
  const input = palette.element.children[0];
  return { palette, input, ran };
}

describe("palette: repeatable commands", () => {
  test("rows carry the repeatable flag", () => {
    const { palette } = build();
    palette.open();
    const rows = paletteRows({
      entries: ENTRIES,
      registry: { has: () => true, can: () => true, status: () => "ready", hintKey: () => null },
      state: {},
      label: (key) => key,
      format: (raw) => raw,
      platform: "other",
    });
    assert.equal(rows.find((row) => row.id === "view.zoom_in").repeatable, true);
    assert.equal(rows.find((row) => row.id === "edit.split").repeatable, undefined);
  });

  test("Enter twice on zoom in runs it twice and the palette stays open", () => {
    const { palette, input, ran } = build();
    palette.open();
    input.value = "zoom in";
    for (const fn of input.listeners.input) fn();
    press(input, "Enter");
    press(input, "Enter");
    assert.deepEqual(ran, ["view.zoom_in", "view.zoom_in"]);
    assert.equal(palette.isOpen(), true);
  });

  test("a normal command closes the palette", () => {
    const { palette, input, ran } = build();
    palette.open();
    input.value = "split";
    for (const fn of input.listeners.input) fn();
    press(input, "Enter");
    assert.deepEqual(ran, ["edit.split"]);
    assert.equal(palette.isOpen(), false);
  });
});
