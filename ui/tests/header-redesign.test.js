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

test("the headers overlay the lanes: a strip and a name pill, expanding on hover", () => {
  // The waveforms run from the rail's right edge; the header is a card that
  // floats over the lane (header redesign, 2026-11-18).
  assert.match(css, /\.th-card\s*\{/);
  assert.match(css, /\.th-strip\s*\{/);
  assert.match(css, /\.track-header:is\(:hover, :focus-within, \.controls-open\) \.th-card/);
  assert.match(source, /setRecording\(active\)/);
});
