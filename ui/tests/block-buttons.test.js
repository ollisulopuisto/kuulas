// Panel actions use the Play / Record language (owner, 2026-10-19): a square-ish block, the
// icon over the label, one action bar at the top of each side panel, no second heading.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = read("../style.css");
const rule = (selector) => {
  const start = css.indexOf(`\n${selector} {`);
  assert.notEqual(start, -1, selector);
  return css.slice(start, css.indexOf("}", start));
};

test(".button.block is a column block with the Play radius, square (76 px)", () => {
  const block = rule(".button.block");
  assert.match(block, /flex-direction:\s*column/);
  assert.match(block, /width:\s*76px/);
  assert.match(block, /height:\s*76px/);
  assert.match(block, /aspect-ratio:\s*1/);
  assert.match(block, /border-radius:\s*var\(--radius-sm\)/);
});

test("secondary blocks are dark raised like Record, the primary stays accent", () => {
  const secondary = rule(".button.block:not(.primary)");
  assert.match(secondary, /background:\s*var\(--surface-raised\)/);
  assert.match(secondary, /border-color:\s*var\(--border-strong\)/);
});

test("the action bar sits at the top of the panel, not as a bottom border bar", () => {
  const bar = rule(".sidebar .panel > .actionbar");
  assert.match(bar, /display:\s*flex/);
  assert.match(bar, /border-bottom/);
  assert.doesNotMatch(bar, /border-top/);
  assert.doesNotMatch(css, /#panel-(history|candidates) > \.actionbar \{/);
});

test("the panel heading is not drawn a second time under the tab strip", () => {
  assert.match(rule(".sidebar .panel > h2"), /clip-path:\s*inset\(50%\)/);
});

const panels = {
  history: read("../history-panel.js"),
  candidates: read("../candidates-panel.js"),
  markers: read("../markers-panel.js"),
  clipboard: read("../clipboard-panel.js"),
};

test("every panel action is a block button", () => {
  assert.match(panels.history, /class: "button block", "data-icon": "undo"/);
  assert.match(panels.history, /class: "button block", "data-icon": "redo"/);
  assert.match(panels.history, /class: "button block primary",\s*"data-icon": "restore"/);
  assert.match(panels.history, /class: "button block",\s*"data-icon": "older"/);
  for (const id of ["find", "preview", "cut", "keep"]) {
    assert.match(panels.candidates, new RegExp(`class: "button block"[^}]*id: "cand-${id}"`));
  }
  assert.match(panels.candidates, /class: "button block primary",\s*"data-icon": "trash"/);
  assert.match(panels.markers, /class: "button block"/);
  assert.match(panels.clipboard, /className = "button block"/);
});

test("the action bar comes first in History, Candidates and Markers", () => {
  assert.match(panels.history, /replaceChildren\(title, bar,/);
  assert.match(panels.candidates, /replaceChildren\(\s*title,\s*actionbar,/);
  assert.match(panels.markers, /class: "actionbar"/);
});

test("dialog and offer buttons are blocks", () => {
  for (const file of ["../export-dialog.js", "../automix-dialog.js", "../locate-dialog.js"]) {
    assert.match(read(file), /button block/, file);
  }
  assert.match(read("../send-copy-dialog.js"), /`button block/);
  assert.match(read("../colab-dialog.js"), /"button block/);
  assert.match(read("../transcript.js"), /"button block primary" : "button block"/);
});
