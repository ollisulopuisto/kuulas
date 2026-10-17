// The design tokens (ui/tokens.css) are checked here, so a cheaper edit cannot
// quietly break contrast or let the two dark blocks or the prototype drift.
// Thresholds: WCAG 2.2 AA, 4.5:1 for text (1.4.3) and 3:1 for graphics and
// control outlines (1.4.11). Spec: docs/design/GUI-DESIGN.md.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const read = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const CSS = read("../tokens.css");
const PROTOTYPE = "../../docs/design/prototype/index.html";

/** The declarations inside the first block that starts with `selector {`. */
export function block(css, selector) {
  const at = css.indexOf(`${selector} {`);
  assert.notEqual(at, -1, `no block ${selector}`);
  let depth = 0;
  let start = -1;
  for (let i = at; i < css.length; i += 1) {
    if (css[i] === "{") {
      depth += 1;
      if (depth === 1) start = i + 1;
    } else if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(start, i);
    }
  }
  throw new Error(`unclosed block ${selector}`);
}

export function declarations(body) {
  const out = new Map();
  const clean = body.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const m of clean.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out.set(m[1], m[2].trim());
  return out;
}

const LIGHT = new Map([
  ...declarations(block(CSS, ":root")),
  ...declarations(CSS.slice(CSS.indexOf("/* -- light"), CSS.indexOf("/* -- dark"))),
]);
const DARK_OS = declarations(block(CSS, ':root:not([data-theme="light"])'));
const DARK = new Map([...LIGHT, ...declarations(block(CSS, ':root[data-theme="dark"]'))]);

function rgb(value) {
  const hex = value.match(/^#([0-9a-f]{6})$/i);
  assert.ok(hex, `not a 6-digit hex colour: ${value}`);
  return [0, 2, 4].map((i) => Number.parseInt(hex[1].slice(i, i + 2), 16) / 255);
}
const linear = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
function luminance(value) {
  const [r, g, b] = rgb(value).map(linear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
export function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT = ["--text", "--text-secondary", "--text-tertiary", "--accent-text"];
const STATUS_TEXT = ["--warn-text", "--danger-text", "--ok-text"];
const SURFACES = [
  "--surface-app",
  "--surface-lane",
  "--surface-lane-current",
  "--surface-panel",
  "--surface-raised",
  "--surface-sunken",
  "--surface-hover",
];
const TRACKS = ["0", "1", "2", "3", "4", "5", "music"];

function pairs() {
  const list = [];
  for (const fg of [...TEXT, ...STATUS_TEXT]) for (const bg of SURFACES) list.push([fg, bg, 4.5]);
  list.push(["--text", "--accent-subtle", 4.5]);
  list.push(["--accent-text", "--accent-subtle", 4.5]);
  list.push(["--text-on-accent", "--accent", 4.5]);
  list.push(["--text-on-accent", "--accent-hover", 4.5]);
  list.push(["--warn-text", "--warn-subtle", 4.5]);
  list.push(["--danger-text", "--danger-subtle", 4.5]);
  for (const bg of ["--surface-panel", "--surface-lane", "--surface-raised"]) {
    list.push(["--focus-ring", bg, 3]);
    list.push(["--border-strong", bg, 3]);
    list.push(["--accent", bg, 3]);
    list.push(["--warn", bg, 3]);
    list.push(["--danger", bg, 3]);
  }
  for (const fg of ["--playhead", "--candidate", "--gain-line", "--selection-outline"])
    list.push([fg, "--surface-lane", 3]);
  for (const n of TRACKS) {
    list.push([`--track-${n}-label`, `--track-${n}-body`, 4.5]);
    list.push([`--track-${n}-wave`, `--track-${n}-body`, 3]);
    list.push([`--track-${n}-edge`, "--surface-lane", 3]);
    list.push(["--selection-outline", `--track-${n}-body`, 3]);
    list.push(["--playhead", `--track-${n}-body`, 3]);
  }
  return list;
}

test("the two dark blocks are identical", () => {
  const explicit = declarations(block(CSS, ':root[data-theme="dark"]'));
  assert.deepEqual([...DARK_OS.entries()], [...explicit.entries()]);
});

test("every light colour token has a dark value and the reverse", () => {
  const colourNames = (map) =>
    [...map.keys()].filter((name) =>
      /^--(surface|border|text-(?!xs|sm|md|lg|xl)|text$|accent|focus-ring|selection|partner|playhead|play-start|gain|automation|ruler-text|ruler-tick|warn|danger|ok|candidate|muted|shadow|track)/.test(
        name,
      ),
    );
  assert.deepEqual(colourNames(DARK_OS).sort(), colourNames(LIGHT).sort());
});

for (const [name, theme] of [
  ["light", LIGHT],
  ["dark", DARK],
]) {
  test(`${name}: every contrast pair meets WCAG AA`, () => {
    const failures = [];
    for (const [fg, bg, min] of pairs()) {
      const ratio = contrast(theme.get(fg), theme.get(bg));
      if (ratio < min) failures.push(`${fg} on ${bg}: ${ratio.toFixed(2)} < ${min}`);
    }
    assert.deepEqual(failures, []);
  });
}

test("the scanner and the contrast maths are not vacuous", () => {
  assert.equal(contrast("#000000", "#ffffff").toFixed(1), "21.0");
  assert.equal(contrast("#777777", "#777777"), 1);
  assert.ok(pairs().length > 100);
  assert.equal(declarations("a{--x: #fff; /* --y: 1 */ --z: 2px;}").size, 2);
});

test("the prototype embeds exactly this token file", () => {
  assert.ok(existsSync(fileURLToPath(new URL(PROTOTYPE, import.meta.url))), "prototype missing");
  const html = read(PROTOTYPE);
  const start = html.indexOf("/* kuulas design tokens.");
  const end = html.indexOf("/* -- end of tokens.css -- */");
  assert.ok(start >= 0 && end > start, "token markers missing in the prototype");
  assert.equal(html.slice(start, end).trim(), CSS.trim());
});
