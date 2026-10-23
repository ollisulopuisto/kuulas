// The LIGHT theme is a soft mid-light grey with high contrast (owner, 2026-10-19:
// "more contrasty, the background less white, more middle grey"). tokens.test.js
// checks WCAG AA for every pair; this file pins the stricter light-theme targets
// so a later change cannot quietly lower them:
//   body text >= 7:1, secondary and status text >= 4.5:1, UI borders, icons,
//   ticks, focus ring, playhead >= 3:1, waveforms >= 3:1 on the lane, and the
//   page, panels and lane are grey, not near-white.
// Values are read from ui/tokens.css (docs/design/GUI-DESIGN.md "Colour roles").
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const CSS = readFileSync(fileURLToPath(new URL("../tokens.css", import.meta.url)), "utf8");

function blockAfter(marker, selector) {
  const start = CSS.indexOf(marker);
  assert.notEqual(start, -1, `no section ${marker}`);
  const open = CSS.indexOf(`${selector} {`, start);
  const close = CSS.indexOf("\n}", open);
  const out = new Map();
  const body = CSS.slice(open, close).replace(/\/\*[\s\S]*?\*\//g, "");
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out.set(m[1], m[2].trim());
  return out;
}
const PRIMITIVES = blockAfter("== 1. primitives", ":root");
const LIGHT = blockAfter("== 2. semantic roles: light", ":root");
const CONSTANTS = blockAfter("== theme-independent", ":root");

function value(name) {
  const raw = LIGHT.get(name) ?? CONSTANTS.get(name);
  assert.notEqual(raw, undefined, `${name} is not a light token`);
  const ref = raw.match(/^var\((--[\w-]+)\)$/);
  return ref ? PRIMITIVES.get(ref[1]) : raw;
}

/** [r, g, b, alpha] in 0..1 from #rrggbb or rgb(r g b / a). */
function parse(text) {
  const hex = text.match(/^#([0-9a-f]{6})$/i);
  if (hex) return [0, 2, 4].map((i) => Number.parseInt(hex[1].slice(i, i + 2), 16) / 255).concat(1);
  const fn = text.match(/^rgb\((\d+) (\d+) (\d+) \/ ([\d.]+)\)$/);
  assert.ok(fn, `cannot parse ${text}`);
  return [fn[1] / 255, fn[2] / 255, fn[3] / 255, Number(fn[4])];
}
/** Colour `name` painted at `alpha` over the opaque colour `over`. */
function over(name, overName, extra = 1) {
  const [r, g, b, a] = parse(value(name));
  const base = parse(value(overName));
  const k = a * extra;
  return [0, 1, 2].map((i) => [r, g, b][i] * k + base[i] * (1 - k));
}
const lin = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
const rgbOf = (name) => parse(value(name)).slice(0, 3);
function ratio(a, b) {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
const on = (fg, bg) => ratio(rgbOf(fg), rgbOf(bg));

const SURFACES = [
  "--surface-app",
  "--surface-lane",
  "--surface-lane-current",
  "--surface-panel",
  "--surface-raised",
  "--surface-sunken",
  "--surface-hover",
  "--surface-active",
];
const TRACKS = ["0", "1", "2", "3", "4", "5", "music"];

function check(fgs, bgs, min, failures) {
  for (const fg of fgs)
    for (const bg of bgs) {
      const r = on(fg, bg);
      if (r < min) failures.push(`${fg} on ${bg}: ${r.toFixed(2)} < ${min}`);
    }
}

test("light: page, panels and lane are grey, not near-white", () => {
  // Relative luminance: white is 1.0, #e0e0e0 is 0.75, #d0d0d0 is 0.63.
  const max = {
    "--surface-app": 0.6,
    "--surface-panel": 0.72,
    "--surface-lane": 0.78,
    "--surface-lane-current": 0.78,
    "--surface-hover": 0.72,
    "--surface-active": 0.6,
  };
  const failures = [];
  for (const [name, limit] of Object.entries(max)) {
    const y = lum(rgbOf(name));
    if (y > limit) failures.push(`${name} luminance ${y.toFixed(2)} > ${limit}`);
  }
  assert.deepEqual(failures, []);
  // Text fields and popovers may stay clearly lighter than the panel, but not white.
  for (const name of ["--surface-sunken", "--surface-raised"]) {
    const y = lum(rgbOf(name));
    assert.ok(y > lum(rgbOf("--surface-panel")), `${name} is lighter than the panel`);
    assert.ok(y < 0.9, `${name} is not white (${y.toFixed(2)})`);
  }
  // The lane is no darker than the panel (waveforms need the lighter ground).
  assert.ok(lum(rgbOf("--surface-lane")) >= lum(rgbOf("--surface-panel")));
});

test("light: text is at least 7:1 (primary) and 4.5:1 (secondary, status) on every surface", () => {
  const failures = [];
  check(["--text", "--signal-file-mark-text"], SURFACES, 7, failures);
  check(["--text-secondary", "--text-tertiary"], SURFACES, 4.5, failures);
  check(["--accent-text", "--warn-text", "--danger-text", "--ok-text"], SURFACES, 4.5, failures);
  check(
    ["--text-secondary"],
    ["--surface-panel", "--surface-lane", "--surface-raised"],
    7,
    failures,
  );
  assert.deepEqual(failures, []);
});

test("light: borders, icons, ticks, focus ring and playhead are at least 3:1", () => {
  const ground = ["--surface-panel", "--surface-lane", "--surface-raised", "--surface-sunken"];
  const failures = [];
  check(
    ["--border-strong", "--focus-ring", "--accent"],
    [...ground, "--surface-hover"],
    3,
    failures,
  );
  // Icons and glyphs are drawn in the secondary text colour or darker.
  check(["--text-secondary", "--gain-line", "--automation-line"], ground, 4.5, failures);
  check(["--ruler-tick"], ["--surface-panel"], 3, failures);
  check(["--play-start", "--signal-provisional"], ground, 4.5, failures);
  check(["--playhead"], ["--surface-lane"], 3.5, failures);
  check(["--signal-selected"], ["--surface-lane"], 7, failures);
  assert.deepEqual(failures, []);
  // Rest borders: visible lines, not hairlines of the panel colour.
  assert.ok(on("--border", "--surface-panel") >= 1.8, "--border on panel");
  assert.ok(on("--border", "--surface-lane") >= 1.6, "--border on lane");
  assert.ok(on("--border-subtle", "--surface-lane") >= 1.25, "--border-subtle on lane");
});

test("light: waveforms and clip edges stand out from the lane; clip labels read on the body", () => {
  const failures = [];
  for (const n of TRACKS) {
    check([`--track-${n}-wave`, `--track-${n}-edge`], ["--surface-lane"], 3, failures);
    for (const body of [`--track-${n}-body`, `--track-${n}-body-alt`]) {
      check([`--track-${n}-wave`], [body], 3, failures);
      check([`--track-${n}-label`], [body], 7, failures);
    }
  }
  assert.deepEqual(failures, []);
});

test("light: the clip body is distinct from the lane it sits on", () => {
  for (const n of TRACKS) {
    const r = on(`--track-${n}-body`, "--surface-lane");
    assert.ok(r >= 1.08, `--track-${n}-body on lane ${r.toFixed(2)}`);
  }
});

test("light: selection, transcript highlight, muted and gate states stay visible", () => {
  const failures = [];
  // The in/out band tints the lane clearly, and its edge colour (accent) reads on the band.
  const band = over("--selection-range", "--surface-lane");
  const bandRatio = ratio(band, rgbOf("--surface-lane"));
  if (bandRatio < 1.3) failures.push(`selection band vs lane ${bandRatio.toFixed(2)} < 1.3`);
  if (ratio(rgbOf("--accent"), band) < 3) failures.push("accent on the selection band < 3");
  // Selected rows and the word highlight: text reads at 7:1, the highlight shows on the panel.
  check(["--text"], ["--accent-subtle"], 7, failures);
  check(["--accent-text"], ["--accent-subtle"], 4.5, failures);
  const hl = ratio(rgbOf("--accent-subtle"), rgbOf("--surface-panel"));
  if (hl < 1.15) failures.push(`accent-subtle vs panel ${hl.toFixed(2)} < 1.15`);
  const cur = ratio(rgbOf("--surface-lane-current"), rgbOf("--surface-lane"));
  if (cur < 1.04) failures.push(`current-lane tint vs lane ${cur.toFixed(2)} < 1.04`);
  // Muted: the hatch shows on the lane and the dimmed wave is still seen (35 % opacity).
  const hatch = ratio(over("--signal-muted-hatch", "--surface-lane"), rgbOf("--surface-lane"));
  if (hatch < 1.3) failures.push(`muted hatch vs lane ${hatch.toFixed(2)} < 1.3`);
  const mutedOpacity = Number(CONSTANTS.get("--signal-muted-opacity"));
  for (const n of TRACKS) {
    const dim = over(`--track-${n}-wave`, "--surface-lane", mutedOpacity);
    const r = ratio(dim, rgbOf("--surface-lane"));
    if (r < 1.35) failures.push(`muted --track-${n}-wave vs lane ${r.toFixed(2)} < 1.35`);
  }
  // Gate: the veil is the lane colour, so a closed gate fades into the lane, never a white sheet.
  assert.equal(value("--signal-gate"), value("--surface-lane"));
  assert.deepEqual(failures, []);
});

test("light: semantic signals keep their relations (red stays red, one hue per meaning)", () => {
  const hue = ([r, g, b]) => {
    const max = Math.max(r, g, b);
    const d = max - Math.min(r, g, b);
    if (d === 0) return -1;
    const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return (h * 60 + 360) % 360;
  };
  for (const name of ["--danger", "--signal-clipping", "--signal-candidate", "--signal-removed"]) {
    assert.equal(value(name), value("--danger"), `${name} is the danger red`);
  }
  assert.ok(Math.abs(hue(rgbOf("--danger")) - 7) < 12, "danger is a warm red");
  assert.ok(Math.abs(hue(rgbOf("--playhead")) - 7) < 15, "the playhead is a warm red");
  assert.ok(hue(rgbOf("--accent")) > 165 && hue(rgbOf("--accent")) < 185, "accent is teal");
  assert.ok(hue(rgbOf("--ok")) > 125 && hue(rgbOf("--ok")) < 160, "ok is green");
  assert.ok(hue(rgbOf("--warn")) > 30 && hue(rgbOf("--warn")) < 50, "warn is amber");
});
