// The form grid (docs/design/FORMS.md) as a lint. Owner, 2026-10-20: "go through all panels
// and modal windows and make sure that texts and input fields are aligned nicely so it's not
// all scattershot." Every dialog and panel form uses the shared classes in ui/style.css
// (section "forms"): one label column, one field column, helper text under the field, check
// rows on the field column, the footer's primary last. These tests pin the tokens and the
// CSS that make the columns line up, and scan ui/*.js (string level, no DOM) for form rows
// built the old, per-dialog way.
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

/** The body of the first `selector {` block after `from` (as tokens.test.js reads it). */
function block(css, selector, from = "") {
  const start = css.indexOf(from);
  assert.notEqual(start, -1, `no section ${from}`);
  const open = css.indexOf(`${selector} {`, start);
  assert.notEqual(open, -1, `no block ${selector} after ${from}`);
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === "{") depth += 1;
    else if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(css.indexOf("{", open) + 1, i);
    }
  }
  throw new Error(`unclosed block ${selector}`);
}

function declarations(body) {
  const out = new Map();
  const clean = body.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const m of clean.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    out.set(m[1], m[2].replace(/\s+/g, " ").trim());
  }
  return out;
}

const UI = fileURLToPath(new URL("..", import.meta.url));
const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const read = (path) => readFileSync(path, "utf8");
const TOKENS = read(join(UI, "tokens.css"));
const STYLE = read(join(UI, "style.css"));
const flat = (text) =>
  text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\s+/g, " ")
    .replace(/\( /g, "(")
    .replace(/ \)/g, ")");

/** The declarations (any property) of the first `selector {` block after `from`. */
function rules(css, selector, from = "-- forms") {
  const out = new Map();
  for (const part of flat(block(css, selector, from)).split(";")) {
    const at = part.indexOf(":");
    if (at > 0) out.set(part.slice(0, at).trim(), part.slice(at + 1).trim());
  }
  return out;
}

const CONSTANTS = declarations(block(TOKENS, ":root", "== theme-independent"));
const COMPACT = declarations(
  block(TOKENS, ':root[data-density="compact"]', "== theme-independent"),
);

test("the form tokens exist in both densities", () => {
  for (const name of [
    "--form-label-w",
    "--form-label-w-panel",
    "--form-col-gap",
    "--form-help-gap",
    "--form-num-w",
    "--check-size",
    "--check-gap",
  ]) {
    assert.ok(CONSTANTS.has(name), `${name} missing from the comfortable block`);
  }
  // Fixed widths, not fractions: a fraction of each container is what drifted per section.
  assert.match(CONSTANTS.get("--form-label-w"), /^\d+px$/);
  assert.match(CONSTANTS.get("--form-label-w-panel"), /^\d+px$/);
  assert.match(COMPACT.get("--form-label-w"), /^\d+px$/);
  assert.match(COMPACT.get("--form-label-w-panel"), /^\d+px$/);
  assert.ok(
    Number.parseInt(CONSTANTS.get("--form-label-w-panel"), 10) <
      Number.parseInt(CONSTANTS.get("--form-label-w"), 10),
    "a side panel's label column is narrower than a dialog's",
  );
  assert.equal(CONSTANTS.get("--form-help-gap"), "var(--space-1)");
});

test("a form row is the label column, then one field column", () => {
  const row = rules(STYLE, ":is(.form-row, .check-row)");
  assert.equal(
    row.get("--form-label-col"),
    "max(0px, calc(var(--form-label-w) - var(--form-card-indent, 0px) - var(--form-sub-indent, 0px)))",
  );
  const grid = rules(STYLE, ".form-row");
  assert.equal(grid.get("display"), "grid");
  assert.equal(grid.get("grid-template-columns"), "var(--form-label-col) minmax(0, 1fr)");
  assert.equal(grid.get("column-gap"), "var(--form-col-gap)");
  assert.equal(grid.get("row-gap"), "var(--form-help-gap)");
  assert.equal(grid.get("align-items"), "start");
  // Everything but the label sits in the field column: help text and messages start at the
  // field's left edge, never under the label.
  assert.equal(rules(STYLE, ".form-row > *").get("grid-column"), "2");
  assert.equal(rules(STYLE, ".form-row > .form-label").get("grid-column"), "1");
  // The label is as tall as a control and centred on it: its text shares the control's line.
  const label = rules(STYLE, ".form-label");
  assert.equal(label.get("min-height"), "var(--control-h)");
  assert.equal(label.get("align-items"), "center");
});

test("a check row's box starts where a field starts, its help where its text starts", () => {
  const check = rules(STYLE, ".check-row");
  // The same x as the field column: label column + the column gap.
  assert.equal(
    check.get("padding-inline-start"),
    "calc(var(--form-label-col) + var(--form-col-gap))",
  );
  assert.equal(check.get("grid-template-columns"), "var(--check-size) minmax(0, 1fr)");
  assert.equal(check.get("column-gap"), "var(--check-gap)");
  assert.equal(check.get("row-gap"), "var(--form-help-gap)");
  assert.equal(rules(STYLE, ".check-row > :is(.form-help, .form-msg)").get("grid-column"), "2");
});

test("nested cards and sub-blocks give back their indent, so the field column holds", () => {
  const card = rules(STYLE, ".form-card");
  assert.equal(card.get("--form-card-indent"), "calc(var(--pad-inline) + 1px)");
  assert.equal(card.get("padding-inline"), "var(--pad-inline)");
  assert.equal(card.get("border"), "1px solid var(--panel-divider)");
  const sub = rules(STYLE, ".form-sub");
  assert.equal(sub.get("--form-sub-indent"), "calc(var(--space-5) + 2px)");
  assert.equal(sub.get("padding-inline-start"), "var(--space-5)");
  assert.equal(sub.get("border-inline-start"), "2px solid var(--panel-divider)");
});

test("side panels use the narrower label column", () => {
  assert.equal(
    rules(STYLE, ":is(.panel, .import-panel)").get("--form-label-w"),
    "var(--form-label-w-panel)",
  );
});

test("dialog footers are right-aligned; actions that keep the dialog open go left", () => {
  const footer = rules(STYLE, ".cheatsheet-footer", "-- forms");
  assert.equal(footer.get("justify-content"), "flex-end");
  assert.equal(
    rules(STYLE, ".cheatsheet-footer > .footer-start + :not(.footer-start)").get(
      "margin-inline-start",
    ),
    "auto",
  );
});

test("no per-dialog two-column grid is left", () => {
  // The 2fr/3fr grids each dialog copied are the scattershot: each one wide by its own box.
  const css = flat(STYLE);
  assert.doesNotMatch(css, /minmax\(0, 2fr\) minmax\(0, 3fr\)/);
  for (const gone of [
    ".automix-row",
    ".automix-label",
    ".silence-row",
    ".silence-label",
    ".record-field",
    ".media-field",
    ".perf-choice",
  ]) {
    assert.ok(!css.includes(`${gone} {`), `${gone} still has its own layout in style.css`);
  }
});

// -- the scan -------------------------------------------------------------------------------

/** Old per-dialog row classes: each may stay as a hook, but only next to its shared class. */
export const LEGACY = {
  "automix-row": "form-row",
  "automix-label": "form-label",
  "automix-cell": "form-field",
  "automix-hint": "form-help",
  "automix-msg": "form-msg",
  "automix-check": "check-row",
  "automix-optcheck": "check-row",
  "automix-section": "form-section",
  "automix-heading": "form-heading",
  "automix-field": "form-row",
  "automix-note": "form-note",
  "automix-inline": "form-inline",
  "automix-group": "form-card",
  "automix-ad": "form-sub",
  "silence-row": "form-row",
  "silence-label": "form-label",
  "silence-cell": "form-field",
  "silence-hint": "form-help",
  "silence-msg": "form-msg",
  "silence-section": "form-section",
  "silence-heading": "form-heading",
  "silence-inline": "form-inline",
  "inspector-field": "form-row",
  "export-row": "form-row",
  "export-choice": "form-choice",
  "media-field": "form-row",
  "media-choice": "form-choice",
  "media-note": ["form-note", "form-help"],
  "perf-choice": "form-row",
  "record-field": "form-row",
  "record-label": "form-label",
  "import-choice": "form-row",
  "cand-filter": "check-row",
  "placeholder-field": "form-row",
  "clip-keep-field": "form-inline",
};

const LITERALS = /(["'`])((?:\\.|(?!\1)[^\\])*)\1/g;

/** Blank comments, keeping offsets: an apostrophe in prose must not open a string. */
function withoutComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, (m, lead) => lead + " ".repeat(m.length - lead.length))
    .replace(/^(\s*)#.*$/gm, (m, lead) => lead + " ".repeat(m.length - lead.length));
}

/** Class strings in a source that hold a legacy class without its shared partner. */
export function strayRows(raw) {
  const source = withoutComments(raw);
  const out = [];
  for (const m of source.matchAll(LITERALS)) {
    const words = m[2].split(/\s+/);
    for (const word of words) {
      const partners = [LEGACY[word] ?? []].flat();
      if (partners.length > 0 && !partners.some((p) => words.includes(p))) {
        out.push(`"${m[2]}" (line ${source.slice(0, m.index).split("\n").length})`);
      }
    }
  }
  return out;
}

test("the scan finds a legacy row class without its shared class", () => {
  assert.deepEqual(strayRows('el("div", "automix-row form-row")'), []);
  assert.equal(strayRows('el("div", "automix-row")').length, 1);
  assert.equal(strayRows('{ className: "inspector-field export-row" }').length, 2);
  assert.deepEqual(strayRows('el("p", "automix-hint form-help", t("x"))'), []);
  assert.deepEqual(strayRows('el("p", "media-note form-help")'), []);
  // Prose with an apostrophe does not hide the next class string.
  assert.equal(strayRows('// the server\'s list\nel("label", "automix-check");').length, 1);
});

const modules = () =>
  readdirSync(UI)
    .filter((name) => name.endsWith(".js"))
    .map((name) => join(UI, name));

test("every dialog and panel form row uses the shared classes", () => {
  const bad = [];
  for (const path of [...modules(), join(ROOT, "src/kuulas/launcher_page.py")]) {
    for (const where of strayRows(read(path))) bad.push(`${path.slice(ROOT.length)}: ${where}`);
  }
  assert.deepEqual(bad, [], "use .form-row / .form-label / .form-field / .check-row");
});

/** The footer's children in append order, by variable name; null when not found. */
export function footerOrder(source) {
  const name =
    source.match(/const (\w+) = \w+\(\s*"div",\s*(?:\{ className: )?"cheatsheet-footer/)?.[1] ??
    source.match(/(\w+)\.className = "cheatsheet-footer/)?.[1];
  if (!name) return null;
  const call = [...source.matchAll(new RegExp(String.raw`\b${name}\.append\(([^;]*)\);`, "g"))];
  if (call.length === 0) return null;
  return call
    .at(-1)[1]
    .replace(/\.\.\.\(\w+ \? \[(\w+)\] : \[\]\)/g, "$1")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

test("in every dialog footer the primary comes last", () => {
  const checked = [];
  for (const path of modules()) {
    const source = read(path);
    if (!source.includes('"cheatsheet-footer')) continue;
    const order = footerOrder(source);
    const primary = source.match(/(\w+)\.dataset\.dialogPrimary = ""/)?.[1];
    if (!order || !primary) continue;
    checked.push(path);
    assert.equal(order.at(-1), primary, `${path}: ${order.join(", ")}`);
  }
  assert.ok(checked.length >= 8, `only ${checked.length} footers found`);
});
