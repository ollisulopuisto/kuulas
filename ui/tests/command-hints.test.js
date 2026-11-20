import assert from "node:assert/strict";
import { test } from "node:test";
import { applyCommandShortcuts } from "../command-shortcuts.js";

const makeNode = (tip) => ({
  dataset: { cmd: "view.fit", ...(tip ? { tip } : {}) },
  attrs: {},
  setAttribute(key, value) {
    this.attrs[key] = value;
  },
  hasAttribute(key) {
    return key in this.attrs;
  },
});
const apply = (node, raw, labels) =>
  applyCommandShortcuts(
    { querySelectorAll: (selector) => (selector === "[data-cmd]" ? [node] : []) },
    [{ id: "view.fit", labelKey: "cmd.view.fit", raw }],
    "mac",
    { t: (key) => labels[key] ?? key },
  );
const en = {
  "cmd.view.fit": "Show whole edit",
  "cmd.view.fit.hint": "Fit the edit into the window",
};
test("command control tip includes its translated name, hint and current key", () => {
  const node = makeNode();
  apply(node, ["F8"], en);
  assert.equal(node.dataset.tip, "Show whole edit · Fit the edit into the window · F8");
});
test("automatic tips follow language changes, remaps and unbinding", () => {
  const node = makeNode();
  apply(node, ["F8"], en);
  apply(node, [], {
    "cmd.view.fit": "Näytä koko versio",
    "cmd.view.fit.hint": "Sovita versio ikkunaan",
  });
  assert.equal(node.dataset.tip, "Näytä koko versio · Sovita versio ikkunaan");
});
test("a custom contextual tip is not overwritten", () => {
  const node = makeNode("Current range: 0:10 to 0:20");
  apply(node, ["F8"], en);
  assert.equal(node.dataset.tip, "Current range: 0:10 to 0:20");
});
test("missing hint falls back to the command name without showing a locale key", () => {
  const node = makeNode();
  apply(node, ["F8"], { "cmd.view.fit": "Show whole edit" });
  assert.equal(node.dataset.tip, "Show whole edit · F8");
});

test("a view can replace a generated tip with a state-specific tip", () => {
  const node = makeNode();
  apply(node, ["F8"], en);
  node.dataset.tip = "Current range: 0:10 to 0:20";
  apply(node, ["F9"], en);
  assert.equal(node.dataset.tip, "Current range: 0:10 to 0:20");
});

test("the app translation pass removes native titles after refreshing command hints", async () => {
  const { readFileSync } = await import("node:fs");
  const { runInNewContext } = await import("node:vm");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const code = source.slice(
    source.indexOf("function translate()"),
    source.indexOf("\nlet noticeTimer"),
  );
  const node = makeNode();
  node.dataset.i18nTitle = "fit.title";
  node.attrs.title = "Old title";
  node.getAttribute = (key) => node.attrs[key] ?? null;
  node.removeAttribute = (key) => {
    delete node.attrs[key];
  };
  Object.defineProperty(node, "title", {
    set(value) {
      node.attrs.title = value;
    },
  });
  const entries = [{ id: "view.fit", labelKey: "cmd.view.fit", raw: ["F8"] }];
  const document = {
    querySelectorAll: (selector) =>
      ["[data-cmd]", "[data-i18n-title]"].includes(selector) ? [node] : [],
  };
  const t = (key) => en[key] ?? key;
  applyCommandShortcuts(document, entries, "mac", { t });
  runInNewContext(`${code}\ntranslate();`, {
    document,
    t,
    applyTabs() {},
    tabKeyEntries: entries,
    applyCommandShortcuts,
    detectPlatform: () => "mac",
  });
  assert.equal(node.hasAttribute("title"), false);
  assert.match(node.dataset.tip, /F8/);
});

test("stateful command controls keep their accessible labels without native titles", async () => {
  const { readFileSync } = await import("node:fs");
  const { runInNewContext } = await import("node:vm");
  const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const loop = source.slice(
    source.indexOf('    const button = $("loop");', source.indexOf("function render(")),
    source.indexOf("    // A new range or a switch while playing"),
  );
  const button = makeNode();
  Object.defineProperty(button, "title", {
    set(value) {
      button.attrs.title = value;
    },
  });
  runInNewContext(loop, {
    $: () => button,
    state: { loop: true },
    keyboard: { registry: { can: () => true } },
    t: (key) => key,
  });
  assert.equal(button.hasAttribute("title"), false);
  assert.equal(button.attrs["aria-label"], "ui.transport.loop_on");
  const scope = source.slice(
    source.indexOf("function updateScopeChip("),
    source.indexOf('  if (chip.kind === "clips")'),
  );
  const el = makeNode();
  el.classList = { toggle() {} };
  Object.defineProperty(el, "title", {
    set(value) {
      el.attrs.title = value;
    },
    get() {
      return el.attrs.title;
    },
  });
  runInNewContext(`${scope}\n}\nupdateScopeChip({project:{}});`, {
    $: () => el,
    scopeChip: () => ({ kind: "clips" }),
    t: (key) => key,
  });
  assert.equal(el.hasAttribute("title"), false);
  assert.equal(el.attrs["aria-label"], "ui.scope.chip_title");
});
