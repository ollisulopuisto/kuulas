import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { nextPanel } from "../focus.js";
import { initialState } from "../store.js";
import { recordOf, restoreFrom, SIDEBAR_TABS } from "../view-memory.js";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
test("six independent tabs keep Clipboard between Markers and Material", () => {
  const html = read("../index.html");
  assert.equal((html.match(/role="tab"/g) || []).length, 6);
  assert.match(html, /id="tab-clipboard"/);
  assert.match(html, /id="panel-clipboard" class="panel"/);
  assert.deepEqual(SIDEBAR_TABS, [
    "inspector",
    "history",
    "markers",
    "clipboard",
    "material",
    "candidates",
  ]);
  assert.equal(nextPanel("clipboard", 1), "material");
  assert.equal(nextPanel("clipboard", -1), "markers");
  assert.doesNotMatch(read("../app.js"), /materialsScope/);
});
test("old unified clipboard view migrates without stealing other destinations", () => {
  const context = { project: { tracks: [] }, width: 500, totalFrames: 0 };
  for (const record of [
    { sidebarTab: "clipboard" },
    { sidebarTab: "material", materialsScope: "clipboard" },
  ]) {
    assert.equal(restoreFrom(record, context).patch.sidebarTab, "clipboard");
  }
  for (const sidebarTab of SIDEBAR_TABS) {
    const record = recordOf({ ...initialState(), sidebarTab });
    assert.equal(restoreFrom(record, context).patch.sidebarTab, sidebarTab);
    assert.equal("materialsScope" in record, false);
  }
  assert.equal(
    restoreFrom({ sidebarTab: "history", materialsScope: "clipboard" }, context).patch.sidebarTab,
    "history",
  );
});
