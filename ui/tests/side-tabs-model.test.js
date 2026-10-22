// The side-panel tab strip never wraps (owner, 2026-10-21: "History" fell onto a second row).
// It degrades in steps: full labels, then tight padding, then only the selected tab keeps its
// label and the others show an icon plus their key (never a bare digit). The pure part: which
// step, and the tooltip / hint text.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { beforeEach, test } from "node:test";
import { fileURLToPath } from "node:url";
import * as i18n from "../i18n.js";
import { ICONS } from "../icons.js";
import { formatCombo } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { tabHint, tabMode, tabTitle } from "../side-tabs-model.js";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const locales = fileURLToPath(new URL("../../src/kuulas/locales/", import.meta.url));
beforeEach(() => {
  const catalog = (lang) => JSON.parse(readFileSync(`${locales}${lang}.json`, "utf8"));
  i18n.setCatalogs({ en: catalog("en"), fi: catalog("fi") });
  i18n.setLanguageNow("en");
});

test("tabMode picks the roomiest step that fits", () => {
  const needed = { full: 400, tight: 330, compact: 280 };
  assert.equal(tabMode(needed, 500), "full");
  assert.equal(tabMode(needed, 400), "full");
  assert.equal(tabMode(needed, 399), "tight");
  assert.equal(tabMode(needed, 330), "tight");
  assert.equal(tabMode(needed, 329), "compact");
  assert.equal(tabMode(needed, 280), "compact");
  assert.equal(tabMode(needed, 279), "minimal");
  assert.equal(tabMode(needed, 0), "minimal");
});

test("tabMode is the narrowest step when nothing is measured yet", () => {
  const nan = Number.NaN;
  assert.equal(tabMode({ full: nan, tight: nan, compact: nan }, 300), "minimal");
});

test("tabTitle is the name with its keys", () => {
  assert.equal(tabTitle("History", ["Alt+5"]), "History (Alt+5)");
  assert.equal(tabTitle("History", ["Alt+5", "F6"]), "History (Alt+5, F6)");
  assert.equal(tabTitle("History", []), "History");
});

test("tabHint is the whole shown key, modifier included, never a bare digit", () => {
  assert.equal(tabHint(["⌥3"]), "⌥3");
  assert.equal(tabHint(["Alt+3", "F6"]), "Alt+3");
  assert.equal(tabHint([]), "");
  const keys = DEFAULT_KEYMAP.filter((e) => e.id.startsWith("panel.show_")).map(
    (e) => e.keys.other,
  );
  for (const key of keys) {
    assert.match(tabHint([formatCombo(key, "mac")]), /^⌥\d$/);
    assert.match(tabHint([formatCombo(key, "other")]), /^Alt\+\d$/);
  }
});

test("each tab has an icon in the set, and the app no longer shortens the hint", () => {
  const html = read("../index.html");
  for (const tab of ["inspector", "candidates", "clipboard", "markers", "history"]) {
    const m = html.match(new RegExp(`id="tab-${tab}"[^>]*>.*?data-icon="([a-z]+)"`));
    assert.ok(m, tab);
    assert.ok(m[1] in ICONS, m[1]);
  }
  assert.equal((html.match(/class="tab-icon"/g) ?? []).length, 5);
  const app = read("../app.js");
  assert.doesNotMatch(app, /keyHint|dataset\.short\b/);
  assert.doesNotMatch(read("../style.css"), /attr\(data-short\)/);
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
  assert.match(css, /\.side-tabs\[data-tabs="minimal"\]/);
  // the key hint is hidden only on the selected tab of the narrowest step (its name is shown)
  const hidden = [...css.matchAll(/([^{}]*\.tab-key[^{]*)\{[^}]*display:\s*none/g)].map((m) =>
    m[1].trim(),
  );
  assert.deepEqual(hidden, [
    '.side-tabs[data-tabs="minimal"] .side-tab[aria-selected="true"] .tab-key',
  ]);
  // icons show only on the unselected tabs of the two narrow steps
  assert.match(
    css,
    /\.side-tabs\[data-tabs="compact"\] \.side-tab:not\(\[aria-selected="true"\]\) \.tab-icon/,
  );
  assert.match(rule(".side-tab .tab-icon"), /display:\s*none/);
  // the selected tab must not change width (no bold swap)
  assert.doesNotMatch(rule('.side-tab[aria-selected="true"]'), /font-weight/);
});

test("every tab has a label and a key-hint span", () => {
  const html = read("../index.html");
  assert.equal((html.match(/class="tab-label"/g) ?? []).length, 5);
  assert.equal((html.match(/class="tab-key"/g) ?? []).length, 5);
  assert.equal((html.match(/class="tab-icon"[^>]*aria-hidden="true"/g) ?? []).length, 5);
});
