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
