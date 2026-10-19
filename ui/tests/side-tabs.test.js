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

test("inspector rows are a two-column grid with full-width controls", () => {
  assert.match(
    rule(".inspector-field"),
    /grid-template-columns:\s*minmax\(0, 2fr\) minmax\(0, 3fr\)/,
  );
  assert.doesNotMatch(css, /\.inspector-field[^{]*\{[^}]*max-width:\s*160px/);
  assert.doesNotMatch(css, /\.inspector-field input\[type="number"\] \{[^}]*width:\s*92px/);
  assert.match(rule('.inspector-field input[type="checkbox"]'), /justify-self:\s*start/);
  assert.match(rule(".inspector-readonly"), /text-align:\s*left/);
});

test("History Undo and Redo are shared .button.block buttons with an icon and a label", () => {
  assert.match(
    historyPanel,
    /const undo = el\("button", \{ type: "button", class: "button block",/,
  );
  assert.doesNotMatch(historyPanel, /const (undo|redo) = el\("button", \{[^}]*ghost/);
  assert.match(historyPanel, /"data-icon": "undo"/);
  assert.match(historyPanel, /"data-icon": "redo"/);
  assert.doesNotMatch(historyPanel, /\\u21B[67]/);
  assert.match(css, /\.button,\n\.play \{[^}]*border:\s*1px solid var\(--button-border\)/);
});

test("every data-icon in the UI names an icon in the set", async () => {
  const { ICONS, iconCss } = await import("../icons.js");
  const sources = ["../index.html", "../history-panel.js", "../candidates-panel.js"];
  const used = sources.flatMap((p) =>
    [...read(p).matchAll(/data-icon"?[:=] ?"([a-z]+)"/g)].map((m) => m[1]),
  );
  assert.ok(used.length >= 10);
  for (const name of used) assert.ok(name in ICONS, name);
  assert.match(iconCss(), /mask-image/);
  assert.doesNotMatch(iconCss(), /http:\/\/(?!www\.w3\.org)/);
});
