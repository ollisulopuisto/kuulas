// The side panel's show/hide switch (owner, 2026-10-21: "i need a way to close the sidebar cos
// otherwise it's too crowded"): the pure logic, and the facts about its wiring that need no
// browser (the command, the menu item, the CSS that gives the timeline the width, the strings).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { CHECKED, MENU } from "../menu-model.js";
import {
  opensSidebar,
  SIDEBAR_KEY,
  sidebarAfter,
  sidebarPref,
  sidebarShown,
  toggleSidebar,
} from "../sidebar-model.js";

const read = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

describe("sidebar state", () => {
  test("shown unless the remembered value says hidden", () => {
    assert.equal(sidebarShown(null), true);
    assert.equal(sidebarShown("shown"), true);
    assert.equal(sidebarShown("junk"), true);
    assert.equal(sidebarShown("hidden"), false);
  });

  test("the remembered value round-trips", () => {
    for (const shown of [true, false]) assert.equal(sidebarShown(sidebarPref(shown)), shown);
    assert.equal(SIDEBAR_KEY, "sidebar");
  });

  test("toggle flips", () => {
    assert.equal(toggleSidebar(true), false);
    assert.equal(toggleSidebar(false), true);
  });
});

describe("which commands need the sidebar", () => {
  test("Help, Auto-Silence options, next/previous panel and the tabs do", () => {
    for (const id of [
      "help.open",
      "app.auto_silence_options",
      "panel.next",
      "panel.previous",
      "panel.show_inspector",
      "panel.show_candidates",
      "panel.show_clipboard",
      "panel.show_markers",
      "panel.show_history",
    ])
      assert.equal(opensSidebar(id), true, id);
  });

  test("others, including the toggle itself, do not", () => {
    for (const id of ["view.toggle_sidebar", "transport.play", "view.fit", "edit.split"])
      assert.equal(opensSidebar(id), false, id);
  });

  test("a command that needs it shows a hidden sidebar; others leave it", () => {
    assert.equal(sidebarAfter(false, "help.open"), true);
    assert.equal(sidebarAfter(false, "transport.play"), false);
    assert.equal(sidebarAfter(true, "transport.play"), true);
    assert.equal(sidebarAfter(true, "help.open"), true);
  });
});

describe("wiring", () => {
  test("view.toggle_sidebar is in the keymap with no default key", () => {
    const entry = DEFAULT_KEYMAP.find((e) => e.id === "view.toggle_sidebar");
    assert.ok(entry);
    assert.deepEqual(entry.keys, { mac: null, other: null });
  });

  test("it is a checked item of the View menu, on while the sidebar shows", () => {
    const view = MENU.find((m) => m.id === "view");
    assert.match(JSON.stringify(view), /view\.toggle_sidebar/);
    const check = CHECKED["view.toggle_sidebar"];
    assert.equal(check({}), true);
    assert.equal(check({ sidebarShown: true }), true);
    assert.equal(check({ sidebarShown: false }), false);
  });

  test("hiding it widens the timeline: the grid drops the side column", () => {
    const css = read("../style.css");
    assert.match(css, /\.editor\[data-sidebar="hidden"\] > \.sidebar\s*\{\s*display:\s*none/);
    assert.match(css, /\.editor\[data-sidebar="hidden"\]\s*\{[^}]*grid-template-areas/);
  });

  test("a close button on the tab strip and in the Auto-Silence header", () => {
    assert.match(read("../index.html"), /class="button ghost icon side-close"/);
    assert.match(read("../silence-panel.js"), /button ghost icon silence-close/);
  });

  test("strings in both languages", () => {
    for (const lang of ["en", "fi"]) {
      const json = JSON.parse(read(`../../src/kuulas/locales/${lang}.json`));
      for (const key of [
        "cmd.view.toggle_sidebar",
        "cmd.view.toggle_sidebar.hint",
        "ui.sidebar.on",
        "ui.sidebar.off",
        "ui.sidebar.close",
      ])
        assert.ok(json[key], `${lang} ${key}`);
    }
  });
});

// Owner's order and matching Cmd/Ctrl-1..6; F6 cycling uses the same tab order.
test("sidebar order agrees across tabs, cycle order, menu and number shortcuts", async () => {
  const { SIDEBAR_TABS } = await import("../view-memory.js");
  const expected = ["inspector", "history", "markers", "clipboard", "candidates", "material"];
  assert.deepEqual(SIDEBAR_TABS, expected);
  const htmlOrder = [...read("../index.html").matchAll(/<button id="tab-([^"]+)"/g)].map(
    (match) => match[1],
  );
  assert.deepEqual(htmlOrder, expected);
  const view = MENU.find((menu) => menu.id === "view");
  const panels = view.items.find((entry) => entry.labelKey === "menu.side_panels");
  assert.ok(panels);
  assert.deepEqual(
    panels.items.map((entry) => entry.id),
    expected.map((name) => `panel.show_${name}`),
  );
  expected.forEach((name, index) => {
    const command = DEFAULT_KEYMAP.find((entry) => entry.id === `panel.show_${name}`);
    assert.deepEqual(command.keys, { mac: `Mod+${index + 1}`, other: `Mod+${index + 1}` });
  });
});
