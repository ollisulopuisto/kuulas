// Interactive chip and status buttons (waveform-gain, speed-chip, follow-arrow,
// series-chip, scope-chip, rec-chip, notice-chip) have terse visual text and must provide accessible names
// (aria-label matching title) so screen reader users understand what action clicking them takes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

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

// The theme button keeps its short visible state at the start of its longer name.
test("theme button in index.html and app.js keeps its accessible name tied to its visible label", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const code = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  assert.match(
    html,
    /id="theme"[^>]*data-i18n-aria-label="ui\.theme\.title"/,
    "theme button in index.html has a translated aria-label fallback",
  );

  assert.match(
    code,
    /function applyTheme[\s\S]*?themeButton\.setAttribute\("aria-label",\s*`\$\{themeButton\.textContent\}\. \$\{themeButton\.title\}`\)/,
    "applyTheme includes the visible theme label and its descriptive title in the accessible name",
  );
});
