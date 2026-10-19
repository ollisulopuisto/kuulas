// The main window's chrome (owner, 2026-10-19): the header carries no Undo/Redo/Import/Export
// buttons (they live in the Edit and File menus, and Undo/Redo at the top of the History panel);
// the corner holds Play and Record; the clock and the in/out/length rows sit in the transcript dock.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const historyPanel = readFileSync(new URL("../history-panel.js", import.meta.url), "utf8");
const has = (id) => new RegExp(`id="${id}"`).test(html);

test("the header has no undo, redo, import or export button", () => {
  for (const id of ["undo", "redo", "import", "export"]) assert.equal(has(id), false, id);
});

test("no code reaches for the removed buttons", () => {
  assert.doesNotMatch(app, /\$\("(undo|redo|import|export)"\)/);
});

test("the corner has Play and Record, the dock has the clock and the range rows", () => {
  const corner = html.slice(html.indexOf('class="corner"'), html.indexOf('id="track-headers"'));
  assert.match(corner, /id="play"/);
  assert.match(corner, /id="record"/);
  assert.doesNotMatch(corner, /id="timecode"/);
  assert.doesNotMatch(corner, /class="rcol"/);
  const dock = html.slice(html.indexOf('id="panel-transcript"'), html.indexOf('class="sidebar"'));
  assert.match(dock, /id="timecode"/);
  assert.match(dock, /id="mark-in"/);
  assert.match(dock, /id="mark-length"/);
});

test("the History panel has Undo and Redo", () => {
  assert.match(historyPanel, /actions\.undo/);
  assert.match(historyPanel, /actions\.redo/);
  assert.match(historyPanel, /canUndo/);
});
