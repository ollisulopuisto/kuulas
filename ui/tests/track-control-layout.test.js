import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
const source = readFileSync(new URL("../tracks.js", import.meta.url), "utf8");
test("track controls reserve equal rails and move values above them", () => {
  assert.match(css, /grid-template-columns: minmax\(0, 1fr\) minmax\(0, 1fr\)/);
  assert.match(css, /grid-template-rows: 12px 24px/);
  assert.match(css, /slider-caption/);
  assert.match(source, /"aria-label": label/);
});
test("loudness numbers have a separate visible line rather than consuming a rail", () => {
  const rule = css.match(
    /\.track-header:not\(\.compact\) \.th-controls \.loudness-readout \{([^}]+)\}/,
  )[1];
  assert.match(rule, /position: absolute/);
  assert.match(rule, /font-size: 9px/);
  assert.match(rule, /top: 32px/);
});
test("merged headers keep the bus caption and existing hidden-pan policy", () => {
  assert.match(source, /querySelector\("\.slider-caption"\)\.textContent = t\("ui.bus.fader"\)/);
  assert.match(css, /\.merged \.th-controls \.slider-control.pan \{\s*display: none/);
});
