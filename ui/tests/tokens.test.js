// The design tokens (ui/tokens.css) and the rules that keep them central, so a
// theme can change without touching a component (docs/design/GUI-DESIGN.md,
// "Tokens" and "Themes"):
//   - three layers: primitives (--p-*) -> semantic roles -> component tokens;
//   - every semantic token of the grammar registry is defined in every theme;
//   - no component file holds a colour literal;
//   - WCAG AA: 4.5:1 for text (1.4.3), 3:1 for graphics and outlines (1.4.11);
//   - the prototype embeds this exact file.
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { SEMANTIC_TOKENS, SIGNALS } from "../grammar.js";

const at = (path) => fileURLToPath(new URL(path, import.meta.url));
const read = (path) => readFileSync(at(path), "utf8");
const CSS = read("../tokens.css");
const PROTOTYPE = "../../docs/design/prototype/index.html";

/** The declarations of the first `selector {` block after `from` (a comment). */
export function block(css, selector, from = "") {
  const start = css.indexOf(from);
  assert.notEqual(start, -1, `no section ${from}`);
  const open = css.indexOf(`${selector} {`, start);
  assert.notEqual(open, -1, `no block ${selector} after ${from}`);
  let depth = 0;
  let body = -1;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === "{") {
      depth += 1;
      if (depth === 1) body = i + 1;
    } else if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(body, i);
    }
  }
  throw new Error(`unclosed block ${selector}`);
}

export function declarations(body) {
  const out = new Map();
  const clean = body.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const m of clean.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    out.set(m[1], m[2].replace(/\s+/g, " ").trim());
  }
  return out;
}

const PRIMITIVES = declarations(block(CSS, ":root", "== 1. primitives"));
const CONSTANTS = declarations(block(CSS, ":root", "== theme-independent"));
const LIGHT = declarations(block(CSS, ":root", "== 2. semantic roles: light"));
const DARK_OS = declarations(
  block(CSS, ':root:not([data-theme="light"])', "== 2. semantic roles: dark, by OS"),
);
const DARK = declarations(block(CSS, ':root[data-theme="dark"]', "chosen explicitly"));
const COMPONENT = declarations(block(CSS, ":root", "== 3. component tokens"));
const THEMES = [
  ["light", LIGHT],
  ["dark", DARK],
];

/** A token's final value in a theme, following var() through the layers. */
function resolve(theme, name, seen = new Set()) {
  assert.ok(!seen.has(name), `var() cycle at ${name}`);
  seen.add(name);
  const value =
    COMPONENT.get(name) ?? theme.get(name) ?? CONSTANTS.get(name) ?? PRIMITIVES.get(name);
  assert.ok(value !== undefined, `${name} is not defined`);
  const only = value.match(/^var\(\s*(--[\w-]+)\s*\)$/);
  return only ? resolve(theme, only[1], seen) : value;
}

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
const BUSES = ["1", "2", "3", "4", "5", "6", "7", "8"];

function pairs() {
  const list = [];
  for (const fg of [...TEXT, ...STATUS_TEXT]) for (const bg of SURFACES) list.push([fg, bg, 4.5]);
  list.push(["--text", "--accent-subtle", 4.5]);
  list.push(["--accent-text", "--accent-subtle", 4.5]);
  list.push(["--text-on-accent", "--accent", 4.5]);
  list.push(["--text-on-accent", "--accent-hover", 4.5]);
  list.push(["--warn-text", "--warn-subtle", 4.5]);
  list.push(["--danger-text", "--danger-subtle", 4.5]);
  list.push(["--signal-drift-text", "--signal-drift", 4.5]);
  list.push(["--signal-file-mark-text", "--signal-file-mark", 4.5]);
  list.push(["--button-primary-text", "--button-primary-bg", 4.5]);
  list.push(["--kbd-text", "--kbd-bg", 4.5]);
  for (const bg of ["--surface-panel", "--surface-lane", "--surface-raised"]) {
    for (const fg of [
      "--focus-ring",
      "--border-strong",
      "--accent",
      "--warn",
      "--danger",
      "--signal-placeholder",
      "--signal-damaged",
      "--signal-added",
      "--signal-note",
      "--signal-candidate",
      "--signal-soft-cut",
      "--signal-sibling",
      "--signal-collateral",
      "--signal-preview",
    ]) {
      list.push([fg, bg, 3]);
    }
  }
  for (const fg of ["--playhead", "--gain-line", "--signal-selected", "--signal-seam"]) {
    list.push([fg, "--surface-lane", 3]);
  }
  for (const n of TRACKS) {
    for (const body of [`--track-${n}-body`, `--track-${n}-body-alt`]) {
      list.push([`--track-${n}-label`, body, 4.5]);
      list.push([`--track-${n}-wave`, body, 3]);
      list.push(["--signal-selected", body, 3]);
      list.push(["--playhead", body, 3]);
      list.push(["--signal-clipping", body, 3]);
    }
    list.push([`--track-${n}-edge`, "--surface-lane", 3]);
  }
  for (const n of BUSES) {
    list.push([`--bus-${n}-text`, "--surface-panel", 4.5]);
    list.push([`--bus-${n}-spine`, "--surface-panel", 3]);
    list.push([`--bus-${n}-spine`, "--surface-lane", 3]);
  }
  for (let i = 1; i <= 6; i += 1) list.push([`--label-${i}`, "--surface-lane", 3]);
  return list;
}

// -- layers --------------------------------------------------------------------

// Separation between adjacent graphics, in addition to the existing >= 3:1
// waveform/body checks. Cover both file zebra tones, not just the default body.
for (const [name, theme] of THEMES) {
  test(`${name}: clip border stays distinct from every waveform and body`, () => {
    const edge = resolve(theme, "--signal-clip-edge");
    const failures = [];
    for (const n of TRACKS) {
      for (const [part, floor] of [
        ["wave", 1.6],
        ["body", 1.5],
        ["body-alt", 1.5],
      ]) {
        const r = contrast(edge, resolve(theme, `--track-${n}-${part}`));
        if (r < floor) failures.push(`${n} ${part}: ${r.toFixed(3)} < ${floor}`);
      }
    }
    assert.deepEqual(failures, []);
    for (const state of ["selected", "gate-lock", "group"]) {
      assert.notEqual(edge, resolve(theme, `--signal-${state}`), state);
    }
  });
}

test("the two dark blocks are identical", () => {
  assert.deepEqual([...DARK_OS.entries()], [...DARK.entries()]);
});

test("every theme defines exactly the registry's semantic tokens", () => {
  const expected = SEMANTIC_TOKENS.filter((name) => !CONSTANTS.has(name)).sort();
  for (const [name, theme] of THEMES) {
    assert.deepEqual([...theme.keys()].sort(), expected, `${name} theme`);
  }
});

test("semantic values reference only primitives; primitives are raw and all used", () => {
  const used = new Set();
  for (const [, theme] of THEMES) {
    for (const [name, value] of theme) {
      assert.doesNotMatch(value, /#[0-9a-f]{3,8}\b|rgb\(|hsl\(/i, `${name} holds a literal`);
      for (const m of value.matchAll(/var\((--[\w-]+)\)/g)) {
        assert.ok(m[1].startsWith("--p-"), `${name} references ${m[1]}, not a primitive`);
        assert.ok(PRIMITIVES.has(m[1]), `${name} references undefined ${m[1]}`);
        used.add(m[1]);
      }
    }
  }
  for (const [name, value] of PRIMITIVES) {
    assert.match(value, /^(#[0-9a-f]{6}|rgb\(\d+ \d+ \d+ \/ [\d.]+\))$/i, name);
    assert.ok(used.has(name), `${name} is never used: delete it`);
  }
});

test("component tokens reference only semantic tokens", () => {
  for (const [name, value] of COMPONENT) {
    const ref = value.match(/^var\((--[\w-]+)\)$/);
    assert.ok(ref, `${name}: ${value} is not a single var()`);
    assert.ok(SEMANTIC_TOKENS.includes(ref[1]), `${name} references ${ref[1]}`);
  }
});

test("every signal's tokens resolve to a value in every theme", () => {
  for (const [themeName, theme] of THEMES) {
    for (const s of SIGNALS) {
      for (const token of s.tokens) {
        const value = resolve(theme, token);
        assert.ok(value.length > 0, `${themeName}: ${s.id} ${token}`);
      }
    }
  }
});

// -- no colour outside the token file --------------------------------------------

function componentFiles(dir = at("..")) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (["tests", "node_modules"].includes(entry.name)) continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...componentFiles(path));
    else if (/\.(js|css|html)$/.test(entry.name) && entry.name !== "tokens.css") out.push(path);
  }
  return out;
}

const LITERAL = /#[0-9a-f]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(/gi;
export function colourLiterals(source) {
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
  // Data-URI icons are masks: their stroke colour is never seen.
  return [...code.replace(/url\("data:[^"]*"\)/g, "").matchAll(LITERAL)].map((m) => m[0]);
}

test("no component file holds a colour literal or a primitive", () => {
  const offenders = [];
  for (const path of componentFiles()) {
    const source = readFileSync(path, "utf8");
    for (const hit of colourLiterals(source)) offenders.push(`${path}: ${hit}`);
    if (/var\(--p-/.test(source)) offenders.push(`${path}: uses a primitive`);
  }
  assert.deepEqual(offenders, []);
});

// -- contrast ------------------------------------------------------------------------

for (const [name, theme] of THEMES) {
  test(`${name}: every contrast pair meets WCAG AA`, () => {
    const failures = [];
    for (const [fg, bg, min] of pairs()) {
      const ratio = contrast(resolve(theme, fg), resolve(theme, bg));
      if (ratio < min) failures.push(`${fg} on ${bg}: ${ratio.toFixed(2)} < ${min}`);
    }
    assert.deepEqual(failures, []);
  });
}

test("the scanners and the maths are not vacuous", () => {
  assert.equal(contrast("#000000", "#ffffff").toFixed(1), "21.0");
  assert.equal(contrast("#777777", "#777777"), 1);
  assert.ok(pairs().length > 150);
  assert.equal(declarations("a{--x: #fff; /* --y: 1 */ --z: 2px;}").size, 2);
  assert.deepEqual(colourLiterals("a { color: #fff; b: rgb(1 2 3); } // #abc"), ["#fff", "rgb("]);
  assert.deepEqual(colourLiterals('m: url("data:image/svg+xml,%23fff rgb(1 2 3)")'), []);
  assert.ok(componentFiles().some((p) => p.endsWith("style.css")));
});

// -- the prototype ---------------------------------------------------------------------

test("the prototype embeds exactly this token file and the pure UI modules", () => {
  assert.ok(existsSync(at(PROTOTYPE)), "prototype missing");
  const html = read(PROTOTYPE);
  const start = html.indexOf("/* kuulas design tokens.");
  const end = html.indexOf("/* -- end of tokens.css -- */");
  assert.ok(start >= 0 && end > start, "token markers missing in the prototype");
  assert.equal(html.slice(start, end).trim(), CSS.trim(), "run: node docs/design/sync-tokens.mjs");
  for (const name of [
    "grammar.js",
    "labels.js",
    "crosstalk.js",
    "motion.js",
    "ab-value.js",
    "help.js",
  ]) {
    const gStart = html.indexOf(`// -- ${name} (copy) --`);
    const gEnd = html.indexOf(`// -- end of ${name} --`);
    assert.ok(gStart >= 0 && gEnd > gStart, `${name} markers missing in the prototype`);
    const copy = read(`../${name}`)
      .replace(/^export /gm, "")
      .trim();
    assert.equal(
      html.slice(gStart, gEnd).replace(`// -- ${name} (copy) --`, "").trim(),
      copy,
      `${name}: run node docs/design/sync-tokens.mjs`,
    );
  }
});

test("the prototype's help panel shows the real help topics", () => {
  const html = read(PROTOTYPE);
  const start = html.indexOf("// -- help topics (copy) --");
  const end = html.indexOf("// -- end of help topics --");
  assert.ok(start >= 0 && end > start, "help topic markers missing in the prototype");
  const json = html
    .slice(start, end)
    .replace("// -- help topics (copy) --", "")
    .trim()
    .replace(/^const HELP_FILES = /, "")
    .replace(/;$/, "");
  const embedded = JSON.parse(json);
  const index = JSON.parse(read("../help/index.json")).topics;
  for (const lang of ["en", "fi"])
    for (const id of index)
      assert.equal(
        embedded[`${lang}/${id}`],
        read(`../help/${lang}/${id}.md`),
        `${lang}/${id}: run node docs/design/sync-tokens.mjs`,
      );
});
