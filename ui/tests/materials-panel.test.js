import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { nextPanel } from "../focus.js";
import { initialState } from "../store.js";
import { recordOf, restoreFrom, SIDEBAR_TABS } from "../view-memory.js";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
test("one Materials destination keeps both original panels and clipboard focus route", () => {
  const html = read("../index.html");
  assert.equal((html.match(/role="tab"/g) || []).length, 5);
  assert.doesNotMatch(html, /id="tab-clipboard"/);
  assert.match(html, /id="materials-recordings"/);
  assert.match(html, /id="panel-clipboard" data-panel="clipboard"/);
  assert.deepEqual(SIDEBAR_TABS, ["inspector", "history", "markers", "material", "candidates"]);
  assert.equal(nextPanel("clipboard", 1), "candidates");
  assert.equal(nextPanel("clipboard", -1), "markers");
  const app = read("../app.js");
  assert.match(app, /if \(name === "clipboard"\)/);
  assert.match(app, /setState\(\{ materialsScope: "clipboard" \}\)/);
});
test("unused recordings are the default, switching scopes never rewrites clipboard content", () => {
  const state = initialState();
  assert.equal(state.materialFilter, "unused");
  assert.equal(state.materialsScope, "recordings");
  const panel = read("../materials-panel.js");
  assert.doesNotMatch(panel, /clipboard\s*=|\.splice\(|\.push\(/);
});
test("old Clipboard tab view migrates to the unified tab and new scope is remembered", () => {
  const context = { project: { tracks: [] }, width: 500, totalFrames: 0 };
  const migrated = restoreFrom({ sidebarTab: "clipboard" }, context).patch;
  assert.equal(migrated.sidebarTab, "material");
  assert.equal(migrated.materialsScope, "clipboard");
  const record = recordOf({
    ...initialState(),
    sidebarTab: "material",
    materialsScope: "clipboard",
  });
  assert.equal(restoreFrom(record, context).patch.materialsScope, "clipboard");
});
