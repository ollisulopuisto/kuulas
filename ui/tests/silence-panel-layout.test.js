// The Auto-Silence panel's layout (owner, 2026-10-21: "input field smaller, slider bigger,
// maybe on different lines"): label and a small number on one line, the slider on its own
// line at the panel's full width, a compact action row. String-level facts, no browser.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const read = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const JS = read("../silence-panel.js");
const CSS = read("../style.css");

test("the slider row is label + number, then the slider on its own line", () => {
  assert.match(JS, /silence-slider-row/);
  const at = JS.indexOf("const sliderRow");
  assert.notEqual(at, -1);
  const append = JS.slice(at, at + 2500).match(/wrap\.append\(([^)]*)\)/);
  assert.ok(append, "the row appends its parts in one call");
  const order = append[1].split(",").map((s) => s.trim());
  assert.ok(order.indexOf("label") < order.indexOf("cell"), "label, then the number cell");
  assert.ok(order.indexOf("cell") < order.indexOf("slider"), "then the slider");
});

test("the slider spans the whole row and is at least 24 px tall", () => {
  const rule = CSS.match(/\.silence-slider-row > input\[type="range"\]\s*\{([^}]*)\}/)?.[1] ?? "";
  assert.match(rule, /grid-column:\s*1 \/ -1/);
  assert.match(rule, /width:\s*100%/);
  const height = rule.match(/height:\s*(\d+)px/);
  assert.ok(height && Number(height[1]) >= 24, "hit area");
});

test("the number fields are small", () => {
  for (const selector of [".silence-slider-row .form-num", ".silence-more .form-num"]) {
    const escaped = selector.replace(/[\\^$.*+?()[\]{}|]/g, "\\$&");
    const rule = CSS.match(new RegExp(`${escaped}[^{]*\\{([^}]*)\\}`))?.[1] ?? "";
    assert.match(rule, /width:\s*calc\(7ch/, selector);
  }
});

test("selector escaping neutralises all regex metacharacters", () => {
  const escapeSelector = (s) => s.replace(/[\\^$.*+?()[\]{}|]/g, "\\$&");
  assert.equal(
    escapeSelector("a(b)[c]+d^e$f.g|h*i+j?k"),
    "a\\(b\\)\\[c\\]\\+d\\^e\\$f\\.g\\|h\\*i\\+j\\?k",
  );
});

test("the actions are normal-height buttons, the primary last", () => {
  assert.doesNotMatch(JS, /button block/);
  assert.match(JS, /bar\.append\(listen, reset, close, accept\)/);
  assert.match(CSS, /\.silence-panel > \.actionbar\s*\{[^}]*flex-wrap:\s*wrap/);
});

test("the ids and data attributes the model uses stay", () => {
  assert.match(JS, /input\.id = `silence-panel-\$\{name\}`/);
  assert.match(JS, /sliders\[name\] = slider/);
});
