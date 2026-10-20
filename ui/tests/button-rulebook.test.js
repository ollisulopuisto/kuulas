// The button rulebook (docs/design/BUTTONS.md) as a lint: every <button> the UI makes
// carries one of the shared button classes, or is a named special widget with a reason.
// Owner, 2026-10-20: "Make EVERY appropriate button follow the design rulebook!" This
// keeps new buttons from drifting back to bare text.
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const UI = fileURLToPath(new URL("..", import.meta.url));
const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const read = (path) => readFileSync(path, "utf8");

/**
 * Buttons that are not `.button`: each a widget with its own design-doc row. A new entry
 * needs a reason here and a line in docs/design/BUTTONS.md ("Special widgets").
 */
export const SPECIAL = {
  play: "Play and Record in the transport corner: the one Play shape (GUI-DESIGN.md 'Transport')",
  chip: "status chips in the top and status bars: a pill, not a button (GUI-DESIGN.md 8.2)",
  "menu-title": "menu bar titles: role=menuitem, menus have their own look",
  "menu-item": "menu and context-menu rows: role=menuitem",
  "side-tab": "the sidebar tab strip: role=tab",
  "ms-button": "the track header M / S toggles: --control-h-sm, neutral / amber fill",
  "track-name": "the track name in its header: a label that renames on double-click",
  tag: "the speech / music kind tag in the track header",
  "bus-chevron": "the bus disclosure chevron",
  mrow: "Alku / Loppu / Pituus rows in the marks corner: a label and a time on one line",
  "lm-clip": "the level meter's clip indicator",
  "clip-main": "a list entry's body (clipboard, markers): the row itself is the button",
  "automix-group-head":
    "a disclosure header (chevron, title, badge): the whole row toggles the group",
  "clip-project": "a project heading in the clipboard list: a disclosure row",
  "source-row": "a source row in the inspector: the row itself is the button",
  "tx-pause": "a pause marker inline in the transcript text, not a tab stop",
  "record-clip": "the record meter's clip indicator",
  "record-stop": "the record view's hold-to-stop control (a ring that fills)",
  "cmd-search-show": "the palette row's pointer-only 'show in menu' hint (aria-hidden)",
  row: "a launcher list row (launcher_page.py): the row itself is the button",
};

const BUTTON = /^button$/;
/** Calls that take "button" without making one. */
const NOT_MAKERS = new Set([
  "createElement",
  "querySelector",
  "querySelectorAll",
  "closest",
  "matches",
  "getElementsByTagName",
]);

function uiModules() {
  return readdirSync(UI)
    .filter((name) => name.endsWith(".js"))
    .map((name) => join(UI, name));
}

/** Blank comments, keeping offsets, so commented-out code and prose do not count. */
function withoutComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, (m, lead) => lead + " ".repeat(m.length - lead.length));
}

const LITERALS = /(["'`])((?:\\.|(?!\1)[^\\])*)\1/g;
const literalsIn = (text) => [...text.matchAll(LITERALS)].map((m) => m[2]);

/** The argument starting at `from` (up to a top-level `,` or `)`). */
function argumentAt(source, from) {
  let depth = 0;
  let quote = null;
  for (let i = from; i < source.length; i++) {
    const c = source[i];
    if (quote) {
      if (c === "\\") i++;
      else if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") quote = c;
    else if ("([{".includes(c)) depth++;
    else if (")]}".includes(c)) {
      if (depth === 0) return source.slice(from, i);
      depth--;
    } else if (c === "," && depth === 0) return source.slice(from, i);
  }
  return source.slice(from);
}

/** The class strings an object literal sets (`class:`, `className:`; shorthand `className`). */
function objectClasses(object, source) {
  const found = [...object.matchAll(/\b(?:class|className)\s*:\s*/g)].flatMap((m) =>
    literalsIn(argumentAt(object, m.index + m[0].length)),
  );
  if (found.length > 0) return found;
  // `{ className, ... }`: the helper's parameter default names the class.
  if (/\bclassName\s*[,}]/.test(object)) {
    const fallback = source.match(/[(,]\s*className\s*=\s*(["'`])([^"'`]*)\1/);
    if (fallback) return [fallback[2]];
  }
  return [];
}

/**
 * Every button a source makes, with the classes it can get: `el("button", "a b")`,
 * `el("button", { class: "a" })`, `document.createElement("button")` + `.className = ...`,
 * and `<button class="...">` in markup or template strings.
 */
export function buttonsIn(raw) {
  const source = withoutComments(raw);
  const out = [];
  const line = (index) => source.slice(0, index).split("\n").length;
  for (const m of source.matchAll(/\b(\w+)\(\s*["']button["']\s*(\)|,\s*)/g)) {
    if (NOT_MAKERS.has(m[1])) continue; // createElement is read below; the rest only look
    if (m[2] === ")") {
      out.push({ line: line(m.index), classes: [] });
      continue;
    }
    const arg = argumentAt(source, m.index + m[0].length).trim();
    let classes = arg.startsWith("{") ? objectClasses(arg, source) : literalsIn(arg);
    // A bare name (`el("button", kind, text)`): the helper's parameter default names it.
    if (/^[A-Za-z_$][\w$]*$/.test(arg)) {
      const fallback = source.match(
        new RegExp(String.raw`[(,]\s*${arg}\s*=\s*(["'\x60])([^"'\x60]*)\1`),
      );
      classes = fallback ? [fallback[2]] : [];
    }
    out.push({ line: line(m.index), classes });
  }
  for (const m of source.matchAll(/(\w+)\s*=\s*document\.createElement\(\s*["']button["']\s*\)/g)) {
    const after = source.slice(m.index, m.index + 1200);
    const set = after.match(new RegExp(String.raw`\b${m[1]}\.className\s*=\s*`));
    const classes = set
      ? literalsIn(argumentAt(after, set.index + set[0].length).split(";")[0])
      : [];
    out.push({ line: line(m.index), classes });
  }
  for (const m of source.matchAll(/<button\b[^>]*>/g)) {
    const attr = m[0].match(/\bclass="([^"]*)"/);
    out.push({ line: line(m.index), classes: attr ? [attr[1]] : [] });
  }
  return out.sort((a, b) => a.line - b.line);
}

/** Why a button breaks the rulebook, or null. Every possible class string must pass. */
export function problem(classes) {
  if (classes.length === 0) return "no class: a bare <button> (use .button and a kind)";
  for (const value of classes) {
    // A template like `button block ${extra}` keeps its literal head.
    const words = value.split(/\s+/).filter((w) => w && !w.includes("$"));
    if (words.some((w) => BUTTON.test(w))) continue;
    if (words.some((w) => w in SPECIAL)) continue;
    return `class "${value}" is neither .button nor a listed special widget`;
  }
  return null;
}

const sources = () => [
  ...uiModules(),
  join(UI, "index.html"),
  join(ROOT, "src/kuulas/launcher_page.py"),
];

// Source text with a template placeholder in it, as the scanned files have.
const EXTRA = "$" + "{extra}";

test("the scanner finds every kind of button creation", () => {
  const sample = [
    'el("button", "button block", t("x"));',
    'el("button", { type: "button", class: "button ghost" });',
    'el(\n  "button",\n  { class: "clip-main" },\n  child,\n);',
    'const b = document.createElement("button");\nb.type = "button";\nb.className = `button ' +
      EXTRA +
      "`.trim();",
    'const naked = document.createElement("button");\nnaked.textContent = "x";',
    '`<button type="button" class="button small">`',
    'el("button", primary ? "button block primary" : "button block", text);',
    'const button = (key, className = "button") => el("button", { type: "button", className });',
  ].join("\n");
  const found = buttonsIn(sample).map((b) => b.classes);
  assert.deepEqual(found, [
    ["button block"],
    ["button ghost"],
    ["clip-main"],
    [`button ${EXTRA}`],
    [],
    ["button small"],
    ["button block primary", "button block"],
    ["button"],
  ]);
  assert.equal(problem([]), "no class: a bare <button> (use .button and a kind)");
  assert.equal(problem([`button ${EXTRA}`]), null);
  assert.match(problem(["fancy"]), /neither/);
});

test("every button in the UI is a .button or a listed special widget", () => {
  const bad = [];
  let count = 0;
  for (const path of sources()) {
    for (const { line, classes } of buttonsIn(read(path))) {
      count++;
      const why = problem(classes);
      if (why) bad.push(`${path.replace(ROOT, "")}:${line}: ${why}`);
    }
  }
  assert.ok(count > 80, `found only ${count} buttons: the scanner lost some`);
  assert.deepEqual(bad, []);
});

test("every special widget is still used, so the allow-list cannot rot", () => {
  const all = sources().map(read).join("\n");
  for (const name of Object.keys(SPECIAL)) {
    assert.match(all, new RegExp(String.raw`["'\s\x60]${name}[\s"'\x60]`), name);
  }
});

test("the rulebook lists every special widget", () => {
  const doc = read(join(ROOT, "docs/design/BUTTONS.md"));
  for (const name of Object.keys(SPECIAL)) assert.match(doc, new RegExp(`\`\\.${name}\``), name);
});

// -- the toast: its action is a real secondary button, its close an icon button ---------------
const html = read(join(UI, "index.html"));
const tag = (id) => html.match(new RegExp(`<button id="${id}"[^>]*>`))?.[0] ?? "";
const classOf = (id) =>
  tag(id)
    .match(/class="([^"]*)"/)?.[1]
    .split(/\s+/) ?? [];

test("the toast action (Show in Finder, Cancel) and Undo are secondary buttons, not ghosts", () => {
  for (const id of ["notice-action", "notice-undo"]) {
    assert.ok(classOf(id).includes("button"), id);
    assert.ok(!classOf(id).includes("ghost"), `${id} must not be a ghost`);
  }
  assert.deepEqual(classOf("notice-close").sort(), ["button", "ghost", "icon"]);
});

test("the import panel's Undo and No are secondary, its close an icon button", () => {
  const panel = read(join(UI, "import-panel.js"));
  assert.match(panel, /button\("ui\.import\.mono_no", \(\) => answerMono\(false\)\)/);
  assert.match(
    panel,
    /button\("ui\.transport\.undo", \(\) => actions\.undo\(\), "button", "undo"\)/,
  );
  assert.match(panel, /"button ghost icon"/);
});

test("status-bar buttons are ghosts in the markup, not only by their place", () => {
  const bar = html.slice(html.indexOf('<footer class="statusbar"'), html.indexOf("</footer>"));
  for (const m of bar.matchAll(/<button\b[^>]*>/g)) {
    const classes = m[0].match(/class="([^"]*)"/)?.[1].split(/\s+/) ?? [];
    if (!classes.includes("button")) continue;
    assert.ok(classes.includes("ghost"), m[0]);
  }
});

test("dialog footers use block buttons (perf, statistics, sync confirm, record)", () => {
  for (const file of ["perf-dialog.js", "stats-dialog.js", "sync-confirm.js"]) {
    assert.match(read(join(UI, file)), /className = `button block \$\{extra\}`/, file);
  }
  assert.match(read(join(UI, "record-view.js")), /el\("button", "button block"\)/);
});

test("the transcript find bar's arrows and close are icon buttons", () => {
  const source = read(join(UI, "transcript.js"));
  assert.match(source, /findButton = \(act, text, kind = "button icon"\)/);
  assert.match(source, /findButton\("close", "×", "button ghost icon"\)/);
});

test("the placeholder editor's Save is primary and comes last, Cancel is secondary", () => {
  const source = read(join(UI, "placeholder-editor.js"));
  assert.match(source, /save\.className = "button primary"/);
  assert.match(source, /cancel\.className = "button"/);
  assert.match(source, /actions\.append\(cancel, save\)/);
});

test("a marker's Delete is marked destructive (danger on hover only)", () => {
  assert.match(
    read(join(UI, "markers-panel.js")),
    /button\("delete", t\("ui\.markers\.delete"\), \(\) => actions\.remove\(item\.id\), \{\s*class: "button ghost danger",\s*\}\)/,
  );
});

// -- the shared CSS: what the rulebook promises ----------------------------------------------
const css = read(join(UI, "style.css"));
const rule = (selector) => {
  const start = css.indexOf(`\n${selector} {`);
  assert.notEqual(start, -1, selector);
  return css.slice(start, css.indexOf("}", start));
};

test("a ghost shows its hit area on hover: a background and a border", () => {
  const hover = rule(".button.ghost:hover:not(:disabled)");
  assert.match(hover, /background:\s*var\(--button-hover-bg\)/);
  assert.match(hover, /border-color:\s*var\(--button-hover-border\)/);
});

test("destructive buttons look secondary at rest and turn danger on hover only", () => {
  assert.equal(css.indexOf("\n.button.danger {"), -1, "no resting danger colour");
  const hover = rule(".button.danger:hover:not(:disabled)");
  assert.match(hover, /color:\s*var\(--danger-text\)/);
  assert.match(hover, /border-color:\s*var\(--danger\)/);
});

test("a small button exists for actions inside reading text (help)", () => {
  assert.match(rule(".button.small"), /height:\s*var\(--control-h-sm\)/);
});

test("the launcher page gets the same rules (they sit inside its copied section)", () => {
  const start = css.indexOf("/* -- buttons and chips");
  const end = css.indexOf(".chip {", start);
  const section = css.slice(start, end);
  for (const selector of [".button.danger:hover", ".button.small", ".button.ghost:hover"]) {
    assert.ok(section.includes(selector), selector);
  }
});
