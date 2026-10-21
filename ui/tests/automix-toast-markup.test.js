// The structured automix toast's markup and CSS (docs/design/TOAST.md): the parts the
// renderer fills exist, the bar is a progressbar, the live region is separate, and the CSS
// animates only transform and opacity, with reduced motion respected.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";

const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const html = read("../index.html");
const css = read("../style.css");

const notice = html.slice(html.indexOf('<div id="notice"'), html.indexOf('<div id="notice-live"'));

describe("automix toast markup", () => {
  test("the rich block and its parts sit inside the notice", () => {
    for (const id of [
      "notice-rich",
      "nr-title",
      "nr-percent",
      "nr-eta",
      "nr-bar",
      "nr-fill",
      "nr-phase",
      "nr-step",
      "nr-track",
      "nr-name",
      "nr-note",
      "nr-pips",
      "nr-stage",
      "nr-count",
    ]) {
      assert.ok(notice.includes(`id="${id}"`), id);
    }
  });

  test("the bar is a labelled progressbar from 0 to 100", () => {
    const bar = notice.match(/<div id="nr-bar"[^>]*>/)[0];
    assert.match(bar, /role="progressbar"/);
    assert.match(bar, /aria-valuemin="0"/);
    assert.match(bar, /aria-valuemax="100"/);
    assert.match(bar, /data-i18n-aria-label="ui\.automix\.toast\.bar"/);
  });

  test("the pips are decoration: the stage is also text", () => {
    assert.match(notice, /<span id="nr-pips"[^>]*aria-hidden="true"/);
  });

  test("the phase announcements have their own live region outside the notice", () => {
    assert.ok(!notice.includes('id="notice-live"'));
    assert.match(html, /<div id="notice-live" class="visually-hidden" aria-live="polite"/);
  });
});

describe("automix toast CSS", () => {
  const rules = (selector) => {
    const out = [];
    const re = /([^{}]+)\{([^{}]*)\}/g;
    for (const match of css.matchAll(re)) {
      if (match[1].includes(selector)) out.push(match[2]);
    }
    return out.join("\n");
  };

  test("the fill moves by transform, never by width", () => {
    const fill = rules(".nr-fill");
    assert.match(fill, /transform-origin:\s*left/);
    assert.ok(!/(^|\s|;)width\s*:\s*\d+%/.test(fill), "no percentage width on the fill");
    for (const match of fill.matchAll(/transition:\s*([^;]+);/g)) {
      assert.match(match[1], /^(transform|opacity|none)\b/, match[1]);
    }
  });

  test("the indeterminate shimmer and the transition stop with reduced motion", () => {
    const blocks = [...css.matchAll(/@media \(prefers-reduced-motion: reduce\)\s*\{/g)];
    const covered = blocks.some((m) => css.slice(m.index, m.index + 400).includes(".nr-fill"));
    assert.ok(covered, "a reduced-motion block names .nr-fill");
    assert.ok(css.includes(':root[data-motion="off"] .nr-fill'));
  });

  test("the detail lines keep their height (no jump when a stage changes)", () => {
    const line = rules(".nr-line");
    assert.match(line, /height:/);
    assert.match(line, /white-space:\s*nowrap/);
  });

  test("narrow windows drop the pips, never the stage text", () => {
    const narrow = css.match(/@media \(max-width: 520px\)\s*\{([\s\S]*?)\n\}/);
    assert.ok(narrow, "a narrow-width block");
    assert.match(narrow[1], /\.nr-pips\s*\{\s*display:\s*none/);
    assert.ok(!/#nr-stage\s*\{\s*display:\s*none/.test(narrow[1]));
  });
});
