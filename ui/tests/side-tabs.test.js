// The sidebar tab labels are never cut with an ellipsis (owner, 2026-10-19), and the
// History panel's Undo / Redo use the app's button language (outlined, icon plus text).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = read("../style.css");
const html = read("../index.html");
const historyPanel = read("../history-panel.js");
const rule = (selector) => {
  const start = css.indexOf(`\n${selector} {`);
  assert.notEqual(start, -1, selector);
  return css.slice(start, css.indexOf("}", start));
};

test("tab labels are not ellipsis-truncated and the row wraps", () => {
  const tab = rule(".side-tab");
  assert.doesNotMatch(tab, /text-overflow/);
  assert.doesNotMatch(tab, /overflow:\s*hidden/);
  assert.match(tab, /flex:\s*0 0 auto/);
  assert.match(rule(".side-tabs"), /flex-wrap:\s*wrap/);
});

test("tabs keep their roles and the selected underline", () => {
  assert.equal((html.match(/role="tab"/g) ?? []).length, 5);
  assert.match(rule('.side-tab[aria-selected="true"]'), /border-bottom-color:\s*var\(--accent\)/);
});

test("History Undo and Redo are shared .button buttons with an icon and a label", () => {
  assert.match(historyPanel, /const undo = el\("button", \{ type: "button", class: "button" \}/);
  assert.doesNotMatch(historyPanel, /const (undo|redo) = el\("button", \{[^}]*ghost/);
  assert.match(historyPanel, /btn-icon/);
  assert.match(css, /\.button,\n\.play \{[^}]*border:\s*1px solid var\(--button-border\)/);
});
