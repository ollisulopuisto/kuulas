// The History tab drawn into a tiny stand-in for the DOM (there is no browser here): the
// rolled-back group, the restore row and its restore point, the margin bracket, the arrow
// keys that open and close groups, and "Go to restore point". It cannot say how it looks.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { beforeEach, describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import * as i18n from "../i18n.js";

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
    this.hidden = false;
    this.type = "";
    this.placeholder = "";
    this.id = "";
    this.style = {};
    this.offsetTop = 0;
    this.offsetHeight = 20;
  }
  append(...nodes) {
    this.children.push(...nodes.filter((n) => n !== ""));
  }
  replaceChildren(...nodes) {
    this.children = [];
    this.append(...nodes);
  }
  setAttribute(name, value) {
    this.attrs[name] = String(value);
  }
  getAttribute(name) {
    return this.attrs[name];
  }
  addEventListener(type, fn) {
    this.listeners[type] = [...(this.listeners[type] ?? []), fn];
  }
  fire(type, event = {}) {
    for (const fn of this.listeners[type] ?? []) fn({ target: this, ...event });
  }
  all() {
    return this.children.flatMap((child) =>
      child instanceof FakeNode ? [child, ...child.all()] : [],
    );
  }
  text() {
    return [this.textContent, ...this.children.map((c) => (c instanceof FakeNode ? c.text() : ""))]
      .filter(Boolean)
      .join(" ");
  }
  contains(node) {
    return node === this || this.all().includes(node);
  }
  closest() {
    return null;
  }
  focus() {
    globalThis.document.activeElement = this;
  }
  scrollIntoView() {}
  select() {}
}

globalThis.document = {
  activeElement: null,
  createElement: (tag) => new FakeNode(tag),
  createElementNS: (_ns, tag) => new FakeNode(tag),
};

const { createHistoryPanel } = await import("../history-panel.js");

const locales = fileURLToPath(new URL("../../src/kuulas/locales/", import.meta.url));
const catalog = (lang) => JSON.parse(readFileSync(`${locales}${lang}.json`, "utf8"));
beforeEach(() => {
  i18n.setCatalogs({ en: catalog("en"), fi: catalog("fi") });
  i18n.setLanguageNow("en");
});

const step = (id, extra = {}) => ({
  id,
  label: `stored ${id}`,
  name: `Step ${id}`,
  created: "2026-10-18T11:00:00Z",
  is_marker: false,
  is_head: false,
  side: "past",
  rolled_back_by: null,
  restore_target: null,
  checkpoint: null,
  run: null,
  ...extra,
});
const NODES = [
  step("R", { side: "head", is_head: true, restore_target: "A", name: "Restored to: Step A" }),
  step("D", { side: "rolled_back", rolled_back_by: "R" }),
  step("C", { side: "rolled_back", rolled_back_by: "R" }),
  step("A"),
];

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function open(nodesOf = () => NODES) {
  let state = { sidebarTab: "history", head: "R", panel: "history" };
  const calls = [];
  const root = new FakeNode("section");
  const panel = createHistoryPanel({
    root,
    api: {
      getHistory: async (query) => {
        calls.push(query);
        return { nodes: query.saved ? [] : nodesOf(), more: false };
      },
    },
    getState: () => state,
    setState: (patch) => {
      state = { ...state, ...patch };
    },
    actions: { restore() {}, undo() {}, redo() {}, showError: (e) => assert.fail(e) },
    now: () => Date.parse("2026-10-18T17:00:00Z"),
  });
  panel.update(state);
  await flush();
  panel.update(state);
  const rowsOf = () => root.all().filter((n) => n.tagName === "li");
  const row = (id) => rowsOf().find((n) => n.dataset.id === id);
  // Keys reach the panel's own listener, as they bubble up from the focused row.
  const key = (k) =>
    root.fire("keydown", { key: k, preventDefault() {}, stopPropagation() {}, target: root });
  return { panel, root, rowsOf, row, key, calls, state: () => state };
}

describe("the History tab after a Restore", () => {
  test("the rolled-back steps are one closed group with an icon and a word", async () => {
    const { row, rowsOf } = await open();
    const group = row("g:rolled_back:D");
    assert.ok(group);
    assert.equal(group.attrs["aria-expanded"], "false");
    assert.equal(group.attrs["aria-description"], "Rolled back");
    assert.match(group.text(), /↩/);
    assert.match(group.text(), /Rolled back 2 steps/);
    assert.equal(row("D"), undefined);
    assert.deepEqual(
      rowsOf().map((n) => n.dataset.id),
      ["R", "g:rolled_back:D", "A"],
    );
  });

  test("the restore row says what it went back to; the target is the restore point", async () => {
    const { row, root } = await open();
    assert.match(row("R").text(), /⤺/);
    assert.match(row("R").text(), /Restored to: Step A/);
    assert.match(row("A").text(), /restore point/);
    const bracket = root.all().find((n) => n.className === "hist-bracket");
    assert.deepEqual(bracket.dataset, { from: "R", to: "A" });
  });

  test("Right opens the group, Left on a step inside closes it again", async () => {
    const { row, key, state } = await open();
    key("ArrowDown");
    assert.equal(state().historySelected, "g:rolled_back:D");
    key("ArrowRight");
    assert.equal(row("g:rolled_back:D").attrs["aria-expanded"], "true");
    assert.ok(row("D").className.includes("dim-rolled_back"));
    assert.equal(row("D").attrs["aria-description"], "Rolled back");
    key("ArrowDown");
    assert.equal(state().historySelected, "D");
    key("ArrowLeft");
    assert.equal(state().historySelected, "g:rolled_back:D");
    assert.equal(row("D"), undefined);
  });

  test("Go to restore point picks the target of the picked restore", async () => {
    const { panel, state } = await open();
    assert.equal(state().historySelected, "R");
    assert.equal(state().historyRestoreTarget, "A");
    assert.equal(await panel.goToRestorePoint(), true);
    assert.equal(state().historySelected, "A");
    assert.equal(state().historyRestoreTarget, null);
    assert.equal(await panel.goToRestorePoint(), false);
  });

  test("All steps | Saved versions is one two-state switch with the active one marked", async () => {
    const { root } = await open();
    const group = root.all().find((n) => n.className === "hist-filter");
    assert.equal(group.attrs.role, "group");
    const [all, saved] = group.children;
    assert.equal(all.textContent, "All steps");
    assert.equal(saved.textContent, "Saved versions");
    assert.equal(all.attrs["aria-pressed"], "true");
    assert.equal(saved.attrs["aria-pressed"], "false");
  });

  test("Saved versions shows a hint whose link switches back to All steps", async () => {
    const { panel, root, calls } = await open();
    const hint = () => root.all().find((n) => n.className === "hist-saved-hint");
    assert.equal(hint().hidden, true);
    panel.showSavedVersions();
    await flush();
    assert.equal(hint().hidden, false);
    assert.match(hint().text(), /Showing saved versions only\. You can restore any step:/);
    assert.equal(calls.at(-1).saved, true);
    const link = hint()
      .all()
      .find((n) => n.tagName === "button");
    assert.equal(link.textContent, "switch to All steps");
    link.fire("click");
    await flush();
    assert.equal(hint().hidden, true);
    assert.equal(calls.at(-1).saved, false);
  });

  test("refresh fetches again at the same head, so a version just saved shows", async () => {
    let list = NODES;
    const { panel, row, calls } = await open(() => list);
    assert.doesNotMatch(row("R").text(), /Saved 14\.32/);
    const before = calls.length;
    list = NODES.map((n) =>
      n.id === "R"
        ? {
            ...n,
            checkpoint: {
              name: "Saved 14.32",
              kind: "manual",
              copy: null,
              created: "2026-10-18T11:32:00Z",
            },
          }
        : n,
    );
    await panel.refresh();
    assert.ok(calls.length > before);
    assert.match(row("R").text(), /Saved 14\.32/);
  });

  test("startRename(id) picks that version and opens its name field", async () => {
    const saved = {
      name: "Saved 14.32",
      kind: "manual",
      copy: null,
      created: "2026-10-18T11:32:00Z",
    };
    const { panel, root, state } = await open(() =>
      NODES.map((n) => (n.id === "A" ? { ...n, checkpoint: saved } : n)),
    );
    assert.equal(state().historySelected, "R");
    assert.equal(panel.startRename("A"), true);
    assert.equal(state().historySelected, "A");
    const field = root.all().find((n) => n.className === "hist-rename");
    assert.equal(field.value, "Saved 14.32");
    assert.equal(panel.startRename("R"), false);
  });

  test("Expand all opens the group", async () => {
    const { panel, row } = await open();
    panel.expandAll();
    assert.equal(row("g:rolled_back:D").attrs["aria-expanded"], "true");
    assert.ok(row("C"));
  });
});
