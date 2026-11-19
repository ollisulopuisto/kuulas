import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");
const source = readFileSync(new URL("../tracks.js", import.meta.url), "utf8");
test("the expanded card lays the level and pan controls out in one row", () => {
  assert.match(css, /\.th-main\s*\n\s*> \.th-controls \{[^}]*display: flex/s);
  assert.match(css, /\.th-card \.slider-control\.pan \{[^}]*width: 28px/s);
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

test("the current track's name pill gets a subtle tint in its track color", () => {
  assert.match(
    css,
    /\.track-header\[data-track\]\.current \.th-main > \.track-name\s*\{[^}]*background:\s*color-mix\(in srgb, var\(--panel-bg\) 80%, var\(--track-colour\)\)/,
  );
});

test("pan arc leaves the bottom quarter open without changing rotary mapping", () => {
  assert.match(css, /conic-gradient\(\s*from 225deg/);
  assert.match(css, /0deg 270deg,\s*transparent 270deg 360deg/);
  assert.match(source, /parts\.pan\.wrap\.classList\.add\("dial"\)/);
});

test("track metadata opens in a popover under the header card", () => {
  // The gain and pan live inside the expanding card; the ".." popover carries
  // only the metadata (header redesign, 2026-11-18).
  assert.match(css, /.track-controls-flyout\s*\{[^}]*position:\s*fixed/s);
  assert.match(css, /.track-controls-flyout\s*\[hidden\]\s*\{\s*display:\s*none/s);
  assert.match(source, /"aria-controls": `track-controls-\$\{id\}`/);
  assert.match(source, /card\.append\(strip, main\)/);
  assert.match(source, /flyout\.append\(metadata\)/);
  assert.match(source, /disclosure\.addEventListener\("keydown"/);
  assert.match(source, /window\.addEventListener\("scroll", positionFlyout, true\)/);
});

test("the collapsed header is a drag strip with M/S plus a separate name pill", () => {
  assert.ok(source.includes('el("div", "th-card")'), "header uses card markup");
  assert.ok(source.includes('el("div", "th-strip")'), "card has a drag strip");
  assert.ok(
    /strip\.append\(handle, buttons, el\("span", "th-rec-dot"/.test(source),
    "strip holds handle, M/S, rec dot",
  );
  assert.ok(
    /\.th-main > \.track-name,\s*\.th-row1 > \.bus-name\s*\{[^}]*border-radius: 999px/s.test(css),
    "name is a pill",
  );
  assert.ok(
    /\.track-header\.recording \.th-rec-dot\s*\{[^}]*display: block/s.test(css),
    "rec dot shows when recording",
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
