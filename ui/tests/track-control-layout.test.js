import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
const source = readFileSync(new URL("../tracks.js", import.meta.url), "utf8");
const tokens = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");

test("channel header width is compact in both densities and toolbar layouts", () => {
  assert.equal((tokens.match(/--heads-w:\s*160px/g) || []).length, 2);
  assert.equal((tokens.match(/--heads-w-min:\s*150px/g) || []).length, 2);
  assert.equal((tokens.match(/--heads-w-max:\s*170px/g) || []).length, 2);
  assert.equal((css.match(/--heads-w:\s*calc\(160px \+ var\(--rail-w\)\)/g) || []).length, 2);
  assert.equal((css.match(/--heads-w-min:\s*calc\(150px \+ var\(--rail-w\)\)/g) || []).length, 2);
});

test("track controls are an overlay opened from the header and an explicit button", () => {
  assert.match(source, /track-controls-trigger/);
  assert.match(source, /t\("ui\.track\.controls\.open"\)/);
  assert.match(source, /el\("section", "track-header track-controls-popover"/);
  assert.match(source, /TRACK_CONTROLS_HOVER_MS = 240/);
  assert.match(source, /window\.setTimeout\([\s\S]{0,180}TRACK_CONTROLS_HOVER_MS/);
  assert.match(css, /\.track-controls-popover\s*\{[^}]*position:\s*fixed/s);
  assert.match(css, /\.track-controls-popover\[hidden\]/);
});

test("track controls reserve equal rails and move values above them", () => {
  assert.match(css, /grid-template-columns: minmax\(0, 1fr\) minmax\(0, 1fr\)/);
  assert.match(css, /grid-template-rows: 12px 24px/);
  assert.match(css, /slider-caption/);
  assert.match(source, /"aria-label": label/);
});
test("loudness numbers are anchored without consuming a rail", () => {
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
test("pan keeps the original rotary control without dotted styling", () => {
  assert.match(source, /parts\.pan\.wrap\.classList\.add\("dial"\)/);
  assert.doesNotMatch(css, /border: 2px dashed var\(--control-colour\)/);
  assert.match(css, /--control-colour: var\(--control-pan\)/);
  assert.doesNotMatch(source, /pan-l|pan-r/);
});
test("collapsed tracks keep mute/solo and role icon beside the name", () => {
  assert.match(css, /\[data-control-lines="1"\]\[data-track\] \.th-top > \.ms \{\s*display: flex/);
  assert.match(
    css,
    /\[data-control-lines="1"\]\[data-track\] \.th-top > \.tag \{\s*display: block/,
  );
});

test("the current track header gets a subtle tint in its track color", () => {
  assert.match(
    css,
    /\.track-header\[data-track\]\.current\s*\{[^}]*background:\s*color-mix\(in srgb, var\(--panel-bg\) 86%, var\(--track-colour\)\)/,
  );
});

test("pan arc leaves the bottom quarter open without changing rotary mapping", () => {
  assert.match(css, /conic-gradient\(\s*from 225deg/);
  assert.match(css, /0deg 270deg,\s*transparent 270deg 360deg/);
  assert.match(source, /parts\.pan\.wrap\.classList\.add\("dial"\)/);
});
