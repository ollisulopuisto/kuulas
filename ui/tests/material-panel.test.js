// The Material tab drawn into a tiny stand-in for the DOM: what rows show and what a click
// reports. How it looks is for a screen.
import assert from "node:assert/strict";
import { beforeEach, describe, test } from "node:test";

class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attrs = {};
    this.listeners = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
    this.title = "";
    this.disabled = false;
    this.type = "";
    this.placeholder = "";
    this.style = {};
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

  click() {
    for (const fn of this.listeners.click ?? []) fn({});
  }

  all() {
    return this.children.flatMap((child) =>
      child instanceof FakeNode ? [child, ...child.all()] : [],
    );
  }
}

globalThis.document = { createElement: (tag) => new FakeNode(tag) };

const { createMaterialPanel } = await import("../material-panel.js");

const row = (id, state, extra = {}) => ({
  id,
  name: `file ${id}`,
  state,
  seconds: 100,
  used_s: state === "unused" ? 0 : 100,
  cut_s: 0,
  unused_s: state === "unused" ? 100 : 0,
  missing: false,
  recorded: false,
  ...extra,
});

let calls;
let panel;
let root;

beforeEach(() => {
  calls = [];
  root = new FakeNode("section");
  const record =
    (name) =>
    (...args) =>
      calls.push([name, ...args]);
  panel = createMaterialPanel({
    root,
    actions: {
      filter: record("filter"),
      text: record("text"),
      copy: record("copy"),
      place: record("place"),
    },
  });
});

const state = (extra = {}) => ({
  material: { status: "ok", rows: [row("a", "used"), row("b", "unused")] },
  materialFilter: "all",
  materialText: "",
  ...extra,
});
const byAction = (action) => root.all().filter((node) => node.dataset.action === action);

describe("the Material tab", () => {
  test("one row per recording shown by the filter", () => {
    panel.update(state());
    assert.equal(byAction("copy").length, 2);
    panel.update(state({ materialFilter: "unused" }));
    assert.equal(byAction("copy").length, 1);
    assert.equal(byAction("copy")[0].dataset.id, "b");
  });

  test("a row's two buttons report its id", () => {
    panel.update(state());
    byAction("copy")[0].click();
    byAction("place")[1].click();
    assert.deepEqual(calls, [
      ["copy", "a"],
      ["place", "b"],
    ]);
  });

  test("a filter button reports the filter and shows which one is on", () => {
    panel.update(state({ materialFilter: "timeline" }));
    const filters = byAction("filter");
    assert.equal(filters.length, 4);
    assert.equal(filters.find((n) => n.dataset.id === "timeline").attrs["aria-pressed"], "true");
    filters.find((n) => n.dataset.id === "takes").click();
    assert.deepEqual(calls, [["filter", "takes"]]);
  });

  test("a missing file is marked and cannot be placed", () => {
    panel.update(
      state({ material: { status: "ok", rows: [row("a", "used", { missing: true })] } }),
    );
    assert.equal(byAction("place")[0].disabled, true);
    assert.equal(byAction("copy")[0].disabled, true);
  });

  test("nothing loaded, an empty project and no match each say so", () => {
    panel.update(state({ material: null }));
    assert.ok(root.all().some((n) => n.textContent === "ui.material.loading"));
    panel.update(state({ material: { status: "ok", rows: [] } }));
    assert.ok(root.all().some((n) => n.textContent === "ui.material.empty"));
    panel.update(state({ materialText: "zzz" }));
    assert.ok(root.all().some((n) => n.textContent === "ui.material.no_match"));
  });
});
