import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
const source = readFileSync(new URL("../tracks.js", import.meta.url), "utf8");
const tokens = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");
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

test("track mixer controls open in an overlay beside stable narrow headers", () => {
  assert.match(tokens, /--heads-w: 160px/);
  assert.match(tokens, /--heads-w-min: 152px/);
  assert.match(css, /.track-controls-flyout\s*\{[^}]*position:\s*fixed/s);
  assert.match(css, /.track-controls-flyout\s*\[hidden\]\s*\{\s*display:\s*none/s);
  assert.match(source, /"aria-controls": `track-controls-\$\{id\}`/);
  assert.match(source, /top\.append\(handle, name, buttons, disclosure\)/);
  assert.match(source, /flyout\.append\(metadata, controls\)/);
  assert.match(source, /disclosure\.addEventListener\("keydown"/);
  assert.match(source, /flyout\.querySelector\([\s\S]*?:not\(\[tabindex="-1"\]\)/);
  assert.match(source, /window\.addEventListener\("scroll", positionFlyout, true\)/);
});

test("the track header name and M/S rail forms a downward tab above the lane", () => {
  assert.ok(source.includes('el("div", "th-top track-tab")'), "track row uses tab markup");
  assert.ok(/\.track-tab::after\s*\{[^}]*border-top:/s.test(css), "tab points down");
  assert.ok(/\.track-tab::after\s*\{[^}]*position:\s*absolute/s.test(css), "tab adds no row");
  assert.ok(
    /\.track-header\[data-track\] \.track-tab\s*\{[^}]*height:\s*28px/s.test(css),
    "tab stays compact",
  );
  assert.ok(
    /\.track-header\.strip\[data-track\] \.track-tab\s*\{[^}]*height:\s*16px/s.test(css),
    "focus strip fits its lane",
  );
});

test("bus headers use the shorter footprint and a rotary pan control", () => {
  const busBuilder = source.slice(
    source.indexOf("function buildBus"),
    source.indexOf("function update"),
  );
  const busUpdate = source.slice(source.indexOf("function update"));
  assert.ok(/pan\.wrap\.classList\.add\("dial"\)/.test(busBuilder), "bus pan is a dial");
  assert.ok(/parts\.pan\.paintDial\(\)/.test(busUpdate), "bus dial tracks its value");
  assert.ok(
    /\.bus-header:not\(\.compact\)\s*\{[^}]*grid-template-rows:\s*28px 28px/s.test(css),
    "bus header uses shorter rows",
  );
  assert.ok(/\.bus-header \.slider-control\.dial/.test(css), "bus dial has rotary styling");
});
