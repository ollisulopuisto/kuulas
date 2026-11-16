import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
const source = readFileSync(new URL("../tracks.js", import.meta.url), "utf8");

test("compact headers show the channel and current gain and pan", () => {
  assert.match(source, /compactSummary\.textContent =/);
  assert.match(source, /formatDb\(track\.gain_db\)/);
  assert.match(source, /panText\(track\.pan\)/);
  assert.match(css, /\.track-compact-summary\s*\{/);
});

test("narrow headers expand their controls to the lane height", () => {
  assert.match(css, /--heads-w: calc\(148px \+ var\(--rail-w\)\)/);
  assert.match(source, /flyout\.style\.height =/);
  assert.match(css, /\.bus-header:hover \.th-controls/);
});
