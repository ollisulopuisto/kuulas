// The waveform gain chip and follow arrow buttons are interactive controls
// whose visual contents are terse (e.g. "×2.5", "◀ 0:12.345"). They must provide
// accessible names (aria-label) so screen reader users understand what action clicking them takes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

test("waveform-gain and follow-arrow buttons in app.js set aria-label matching their title", () => {
  const code = readFileSync(new URL("../app.js", import.meta.url), "utf8");

  // In the waveformGain touched branch:
  // button.setAttribute("aria-label", button.title) or equivalent ensures accessible name
  assert.match(
    code,
    /\$\("waveform-gain"\)[\s\S]*?aria-label/,
    "waveform-gain chip sets aria-label",
  );

  // In updateFollowChip:
  // arrow.setAttribute("aria-label", arrow.title) or equivalent ensures accessible name
  assert.match(
    code,
    /arrow\.setAttribute\("aria-label",\s*arrow\.title\)/,
    "follow-arrow sets aria-label matching its title",
  );
});
