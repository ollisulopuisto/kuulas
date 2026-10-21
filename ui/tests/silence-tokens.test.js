// The tokens of the silent-state language (docs/design/SILENCE-VISUALS.md), in both themes:
//   --signal-silent-body  the light darkening of a silent clip's body (alpha): the outline-only
//                         wave stays >= 3:1 on it, and it is a visible step from the body;
//   --signal-gate-lock    the closed padlock (Auto-Silence closed this stretch);
//   --signal-gate-open    the open padlock (the clip keeps the mic open).
// The icons sit on a --surface-panel chip; they must read >= 3:1 there (WCAG 1.4.11), on
// the lane, and on every clip body plain and toned, so the chip is a help, not a crutch.
// Missing media reuses --signal-damaged on --signal-damaged-fill.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { SEMANTIC_TOKENS, signal } from "../grammar.js";

const CSS = readFileSync(fileURLToPath(new URL("../tokens.css", import.meta.url)), "utf8");
const PRIMITIVES = new Map(
  [...CSS.matchAll(/(--p-[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]),
);
function block(marker, selector) {
  const open = CSS.indexOf(`${selector} {`, CSS.indexOf(marker));
  const close = CSS.indexOf("\n}", open);
  const body = CSS.slice(open, close).replace(/\/\*[\s\S]*?\*\//g, "");
  return new Map([...body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
}
const THEMES = {
  light: block("== 2. semantic roles: light", ":root"),
  dark: block("chosen explicitly", ':root[data-theme="dark"]'),
};
function value(theme, name) {
  const raw = THEMES[theme].get(name) ?? PRIMITIVES.get(name);
  assert.ok(raw, `${name} is not defined in ${theme}`);
  const ref = raw.match(/^var\((--[\w-]+)\)$/);
  return ref ? value(theme, ref[1]) : raw;
}
function parse(text) {
  const hex = text.match(/^#([0-9a-f]{6})$/i);
  if (hex) return [0, 2, 4].map((i) => Number.parseInt(hex[1].slice(i, i + 2), 16) / 255).concat(1);
  const fn = text.match(/^rgb\((\d+) (\d+) (\d+) \/ ([\d.]+)\)$/);
  assert.ok(fn, `cannot parse ${text}`);
  return [fn[1] / 255, fn[2] / 255, fn[3] / 255, Number(fn[4])];
}
const rgb = (theme, name) => parse(value(theme, name)).slice(0, 3);
function over(theme, fg, base) {
  const [r, g, b, a] = parse(value(theme, fg));
  return [r, g, b].map((c, i) => c * a + base[i] * (1 - a));
}
const lin = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
function ratio(a, b) {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
const TRACKS = ["0", "1", "2", "3", "4", "5", "music"];
const BODIES = TRACKS.flatMap((n) => [`--track-${n}-body`, `--track-${n}-body-alt`]);
const NEW = ["--signal-silent-body", "--signal-gate-lock", "--signal-gate-open", "--signal-group"];
// Owner, 2026-10-21 (after v26.10.20.35): the toned body was too close to the open body. The
// step must be clearly visible; WCAG's ratio compresses dark colours, so dark asks less.
const MIN_STEP = { light: 1.5, dark: 1.2 };

test("the new tokens are registered and defined in both themes", () => {
  for (const name of NEW) {
    assert.ok(SEMANTIC_TOKENS.includes(name), name);
    for (const theme of Object.keys(THEMES)) assert.ok(value(theme, name), `${theme} ${name}`);
  }
  assert.ok(signal("gate").tokens.includes("--signal-gate-lock"));
  assert.ok(signal("ungated").tokens.includes("--signal-gate-open"));
  assert.ok(signal("muted").tokens.includes("--signal-silent-body"));
  assert.ok(!signal("gate").tokens.includes("--signal-muted-hatch"), "the gate is not hatched");
  assert.ok(!signal("muted").tokens.includes("--signal-muted-hatch"), "a mute is not hatched");
});

for (const theme of Object.keys(THEMES)) {
  test(`${theme}: the silent outline (label colour) reads on the toned body; the step is clear`, () => {
    const failures = [];
    for (const n of TRACKS) {
      for (const part of ["body", "body-alt"]) {
        const body = rgb(theme, `--track-${n}-${part}`);
        const toned = over(theme, "--signal-silent-body", body);
        const line = ratio(rgb(theme, `--track-${n}-label`), toned);
        if (line < 3) failures.push(`outline ${n} on toned ${part}: ${line.toFixed(2)}`);
        const step = ratio(body, toned);
        if (step < MIN_STEP[theme]) failures.push(`tone step on ${n} ${part}: ${step.toFixed(3)}`);
        if (step > 2) failures.push(`tone too strong on ${n} ${part}: ${step.toFixed(3)}`);
      }
    }
    assert.deepEqual(failures, []);
  });

  test(`${theme}: the padlocks read at 3:1 on the chip, the lane and every body, plain and toned`, () => {
    const failures = [];
    for (const icon of ["--signal-gate-lock", "--signal-gate-open"]) {
      const fg = rgb(theme, icon);
      const grounds = [
        ["--surface-panel", rgb(theme, "--surface-panel")],
        ["--surface-lane", rgb(theme, "--surface-lane")],
        ...BODIES.map((b) => [b, rgb(theme, b)]),
        ...BODIES.map((b) => [`toned ${b}`, over(theme, "--signal-silent-body", rgb(theme, b))]),
      ];
      for (const [name, ground] of grounds) {
        const r = ratio(fg, ground);
        if (r < 3) failures.push(`${icon} on ${name}: ${r.toFixed(2)}`);
      }
    }
    assert.deepEqual(failures, []);
  });

  test(`${theme}: the closed and open padlocks, and the preview, are three different colours`, () => {
    const lock = value(theme, "--signal-gate-lock");
    const open = value(theme, "--signal-gate-open");
    const preview = value(theme, "--signal-preview");
    assert.equal(new Set([lock, open, preview]).size, 3);
  });

  test(`${theme}: the group outline and the stretch edges read on the lane and the bodies`, () => {
    const failures = [];
    for (const fg of ["--signal-group", "--signal-gate-lock"]) {
      for (const bg of ["--surface-lane", ...BODIES]) {
        const r = ratio(rgb(theme, fg), rgb(theme, bg));
        if (r < 3) failures.push(`${fg} on ${bg}: ${r.toFixed(2)}`);
      }
    }
    assert.notEqual(value(theme, "--signal-group"), value(theme, "--signal-selected"));
    assert.notEqual(value(theme, "--signal-group"), value(theme, "--signal-gate-lock"));
    assert.deepEqual(failures, []);
  });

  test(`${theme}: missing media's sign reads on its fill`, () => {
    const r = ratio(rgb(theme, "--signal-damaged"), rgb(theme, "--signal-damaged-fill"));
    assert.ok(r >= 3, `damaged on damaged-fill ${r.toFixed(2)}`);
  });
}
