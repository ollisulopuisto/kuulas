// Interactive chip and status buttons (waveform-gain, speed-chip, follow-arrow, follow-chip,
// series-chip, scope-chip, rec-chip, notice-chip) have terse visual text and must provide accessible names
// (aria-label matching title) so screen reader users understand what action clicking them takes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

test("follow-chip in index.html and app.js sets aria-label matching its title", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const code = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(
    html,
    /id="follow-chip"[^>]*data-i18n-aria-label="ui\.view\.follow_chip_title"/,
    "follow-chip in index.html has data-i18n-aria-label matching ui.view.follow_chip_title",
  );

  assert.match(
    code,
    /function updateFollowChip[\s\S]*?chip\.setAttribute\("aria-label",\s*chip\.title\)/,
    "follow-chip in app.js sets aria-label matching chip.title",
  );
});

test("notice-chip in index.html and app.js sets aria-label matching its title", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const code = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(
    html,
    /id="notice-chip"[^>]*data-i18n-aria-label="ui\.notice\.chip_title"/,
    "notice-chip in index.html has data-i18n-aria-label matching ui.notice.chip_title",
  );

  assert.match(
    code,
    /function paintNoticeChip[\s\S]*?chip\.setAttribute\("aria-label",\s*chip\.title\)/,
    "notice-chip in app.js sets aria-label matching chip.title",
  );
});

test("waveform-gain, speed-chip, follow-arrow, series-chip, and scope-chip in app.js set aria-label matching their title", () => {
  const code = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  // In the waveformGain touched branch:
  // button.setAttribute("aria-label", button.title) or equivalent ensures accessible name
  assert.match(
    code,
    /\$\("waveform-gain"\)[\s\S]*?aria-label/,
    "waveform-gain chip sets aria-label",
  );

  // In the speed touched branch:
  // speed-chip sets aria-label matching chip.title so screen readers announce full description
  assert.match(
    code,
    /\$\("speed-chip"\)[\s\S]*?setAttribute\("aria-label",\s*chip\.title\)/,
    "speed-chip sets aria-label matching chip.title",
  );

  // In updateFollowChip:
  // arrow.setAttribute("aria-label", arrow.title) or equivalent ensures accessible name
  assert.match(
    code,
    /arrow\.setAttribute\("aria-label",\s*arrow\.title\)/,
    "follow-arrow sets aria-label matching its title",
  );

  // In updateSeriesChip:
  assert.match(
    code,
    /function updateSeriesChip[\s\S]*?el\.setAttribute\("aria-label",\s*el\.title\)/,
    "series-chip sets aria-label matching el.title",
  );

  // In updateScopeChip:
  assert.match(
    code,
    /function updateScopeChip[\s\S]*?el\.setAttribute\("aria-label",\s*el\.title\)/,
    "scope-chip sets aria-label matching el.title",
  );
});

test("rec-chip in record-view.js sets aria-label matching its title", () => {
  const code = readFileSync(new URL("../record-view.js", import.meta.url), "utf8");
  assert.match(
    code,
    /function renderChip[\s\S]*?chip\.setAttribute\("aria-label",\s*chip\.title\)/,
    "rec-chip sets aria-label matching chip.title",
  );
});

test("theme button in index.html and app.js sets aria-label matching its title", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const code = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(
    html,
    /id="theme"[^>]*data-i18n-aria-label="ui\.theme\.title"/,
    "theme button in index.html has data-i18n-aria-label matching ui.theme.title",
  );

  assert.match(
    code,
    /function applyTheme[\s\S]*?\$\("theme"\)\.setAttribute\("aria-label",\s*\$\("theme"\)\.title\)/,
    "applyTheme in app.js sets aria-label matching title",
  );
});

test("follow button includes the selected mode in its accessible name", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const code = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(
    html,
    /id="follow"[^>]*data-i18n-aria-label="ui\.view\.follow_title"/,
    "follow button in index.html has data-i18n-aria-label matching ui.view.follow_title",
  );

  assert.match(
    code,
    /\$\("follow"\)\.setAttribute\("aria-label",\s*`\$\{\$\("follow"\)\.textContent\}\. \$\{\$\("follow"\)\.title\}`\)/,
    "app.js sets aria-label matching title on follow button",
  );
});

test("record button in index.html and record-view.js provides aria-label in idle state", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const code = readFileSync(new URL("../record-view.js", import.meta.url), "utf8");

  assert.match(html, /id="record"[^>]*data-i18n-aria-label="ui\.transport\.record"/);
  assert.match(code, /recordButton\.setAttribute\("aria-label",\s*t\("ui\.transport\.record"\)\)/);
});

test("follow mode changes update the actual rendered accessible name", () => {
  const code = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const start = code.indexOf('  if (touched("followMode", "followPaused")) {');
  const end = code.indexOf('  if (touched("showGates"))', start);
  const render = new Function("state", "$", "touched", "t", code.slice(start, end));
  const button = { textContent: "", title: "", attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } };
  const translations = { "ui.view.follow_page": "Follow page", "ui.view.follow_continuous": "Follow continuously", "ui.view.follow_title": "Choose follow mode" };
  render({ followMode: "page", followPaused: false }, () => button, () => true, key => translations[key]);
  assert.equal(button.attrs["aria-label"], "Follow page. Choose follow mode");
  render({ followMode: "continuous", followPaused: true }, () => button, () => true, key => translations[key]);
  assert.equal(button.attrs["aria-label"], "Follow continuously. Choose follow mode");
  assert.equal(button.attrs["aria-pressed"], "true");
});
