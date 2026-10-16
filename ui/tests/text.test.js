// Source scans: the checks that keep untranslated text out of ui/ (WP33, R39).
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const UI = fileURLToPath(new URL("..", import.meta.url));
const EN = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../src/kuulas/locales/en.json", import.meta.url)), "utf8"),
);

function uiModules(dir = UI) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "tests" || entry.name === "node_modules") continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...uiModules(path));
    else if (entry.name.endsWith(".js")) out.push(path);
  }
  return out;
}

// Comments are prose, not UI text: blank them, keeping line numbers.
function withoutComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

const KEY_USE = /(?<![\w.$])t\(\s*(["'`])([^"'`$]+)\1/g;

export function usedKeys(source) {
  return [...withoutComments(source).matchAll(KEY_USE)].map((m) => m[2]);
}

const LITERAL = String.raw`(["'\x60])((?:\\.|(?!\1)[^\\])*)\1`;
const PROPERTY = new RegExp(
  String.raw`\.(?:textContent|innerHTML|innerText|outerHTML|title|placeholder|ariaLabel)\s*(?:\+)?=\s*${LITERAL}`,
  "g",
);
const ATTRIBUTE = new RegExp(
  String.raw`setAttribute\(\s*["'](?:aria-label|title|placeholder|alt)["']\s*,\s*${LITERAL}`,
  "g",
);
const QUOTED_ATTRIBUTE = new RegExp(
  String.raw`\[\s*["'](?:aria-label|title|placeholder)["']\s*\]\s*=\s*${LITERAL}`,
  "g",
);

export function literalTexts(source) {
  const code = withoutComments(source);
  const found = [];
  for (const pattern of [PROPERTY, ATTRIBUTE, QUOTED_ATTRIBUTE]) {
    for (const m of code.matchAll(pattern)) {
      const text = m[2].replace(/\$\{[^}]*\}/g, "");
      if (/\p{L}/u.test(text)) {
        found.push({ line: code.slice(0, m.index).split("\n").length, text: m[2] });
      }
    }
  }
  return found;
}

test("every t(...) key used in ui/ exists in en.json", () => {
  const missing = [];
  for (const path of uiModules()) {
    for (const key of usedKeys(readFileSync(path, "utf8"))) {
      if (!(key in EN)) missing.push(`${path}: ${key}`);
    }
  }
  assert.deepEqual(missing, []);
});

test("no ui module assigns literal text with letters to a visible property", () => {
  const offenders = [];
  for (const path of uiModules()) {
    for (const hit of literalTexts(readFileSync(path, "utf8"))) {
      offenders.push(`${path}:${hit.line} ${JSON.stringify(hit.text)}`);
    }
  }
  assert.deepEqual(offenders, []);
});

// "@{" stands for a template placeholder, which Biome flags inside a plain string.
const sample = (text) => text.replaceAll("@{", `${String.fromCharCode(36)}{`);

test("the scanners see what they claim to (they are not vacuous)", () => {
  const bad = [
    'el.textContent = "Save";',
    "el.innerHTML = '<b>Save</b>';",
    sample("el.title = `Save @{n}`;"),
    'el.placeholder = "Name";',
    'el.setAttribute("aria-label", "Close");',
    'el["aria-label"] = "Close";',
    'el.textContent += "more";',
  ];
  for (const line of bad) assert.equal(literalTexts(line).length, 1, line);
  const fine = [
    'el.textContent = t("x");',
    'el.textContent = "";',
    'el.textContent = "12:34";',
    sample("el.textContent = `@{a}:@{b}`;"),
    '// el.textContent = "Save";',
    'el.setAttribute("aria-label", t("close"));',
    'el.className = "button";',
  ];
  for (const line of fine) assert.deepEqual(literalTexts(line), [], line);
  assert.deepEqual(usedKeys('x = t("a.b") + t(`c.d`, {n: 1}); // t("no.thanks")\nnot("e.f")'), [
    "a.b",
    "c.d",
  ]);
  assert.deepEqual(usedKeys("e.target('x.y'); format('q')"), []);
});
