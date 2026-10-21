// The side-panel tab strip never wraps (owner, 2026-10-21: "History" fell onto a second row).
// It degrades in steps: full labels, then tight padding, then only the selected tab keeps its
// label and the others show their Alt+digit. The pure part: which step, and the tooltip text.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { keyHint, tabMode, tabTitle } from "../side-tabs-model.js";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

test("tabMode picks the roomiest step that fits", () => {
  const needed = { full: 400, tight: 330 };
  assert.equal(tabMode(needed, 500), "full");
  assert.equal(tabMode(needed, 400), "full");
  assert.equal(tabMode(needed, 399), "tight");
  assert.equal(tabMode(needed, 330), "tight");
  assert.equal(tabMode(needed, 329), "compact");
  assert.equal(tabMode(needed, 0), "compact");
});

test("tabMode is compact when nothing is measured yet", () => {
  assert.equal(tabMode({ full: Number.NaN, tight: Number.NaN }, 300), "compact");
});

test("tabTitle is the name with its keys", () => {
  assert.equal(tabTitle("History", ["Alt+5"]), "History (Alt+5)");
  assert.equal(tabTitle("History", ["Alt+5", "F6"]), "History (Alt+5, F6)");
  assert.equal(tabTitle("History", []), "History");
});

test("keyHint is the key without its modifiers", () => {
  assert.equal(keyHint("Alt+3"), "3");
  assert.equal(keyHint("⌥3"), "3");
  assert.equal(keyHint(undefined), "");
});

test("Alt+1..Alt+5 are the tab keys, none needing AltGr or Shift+digit", () => {
  const keys = DEFAULT_KEYMAP.filter((e) => e.id.startsWith("panel.show_")).map(
    (e) => e.keys.other,
  );
  assert.deepEqual(keys, ["Alt+1", "Alt+2", "Alt+3", "Alt+4", "Alt+5"]);
});

test("the strip is one row at every step", () => {
  const css = read("../style.css");
  const rule = (s) => css.slice(css.indexOf(`\n${s} {`), css.indexOf("}", css.indexOf(`\n${s} {`)));
  assert.doesNotMatch(rule(".side-tabs"), /flex-wrap:\s*wrap/);
  assert.match(rule(".side-tabs"), /flex-wrap:\s*nowrap/);
  assert.match(rule(".side-tab"), /white-space:\s*nowrap/);
  assert.match(css, /\.side-tabs\[data-tabs="tight"\]/);
  assert.match(css, /\.side-tabs\[data-tabs="compact"\]/);
  // the key hint is never hidden, at any step
  assert.doesNotMatch(css, /\.tab-key[^{]*\{[^}]*display:\s*none/);
  // the selected tab must not change width (no bold swap)
  assert.doesNotMatch(rule('.side-tab[aria-selected="true"]'), /font-weight/);
});

test("every tab has a label and a key-hint span", () => {
  const html = read("../index.html");
  assert.equal((html.match(/class="tab-label"/g) ?? []).length, 5);
  assert.equal((html.match(/class="tab-key"/g) ?? []).length, 5);
});
