// The View switches of the toolbar (WP86): show it, show text on its buttons, reset it.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { CHECKED, MENU, menuTargets } from "../menu-model.js";
import { otherMode } from "../toolbar-prefs.js";

const IDS = ["view.toolbar", "view.toolbar_labels", "view.toolbar_reset", "view.toolbar_add"];
const catalog = (lang) =>
  JSON.parse(
    readFileSync(
      fileURLToPath(new URL(`../../src/kuulas/locales/${lang}.json`, import.meta.url)),
      "utf8",
    ),
  );

describe("the commands", () => {
  test("are in the keymap with no default key (the menu and the palette reach them)", () => {
    for (const id of IDS) {
      const entry = DEFAULT_KEYMAP.find((e) => e.id === id);
      assert.ok(entry, id);
      assert.deepEqual(entry.keys, { mac: null, other: null }, id);
    }
  });

  test("are in the View menu", () => {
    const view = MENU.find((menu) => menu.id === "view");
    const inView = new Set(menuTargets([view]));
    for (const id of IDS) assert.ok(inView.has(id), id);
  });

  test("have a name and a hint in English and Finnish", () => {
    for (const lang of ["en", "fi"]) {
      const messages = catalog(lang);
      for (const id of IDS) {
        assert.ok(messages[`cmd.${id}`], `${lang} cmd.${id}`);
        assert.ok(messages[`cmd.${id}.hint`], `${lang} cmd.${id}.hint`);
      }
      assert.ok(messages["menu.toolbar"], `${lang} menu.toolbar`);
      assert.ok(messages["ui.toolbar.reset_done"], `${lang} ui.toolbar.reset_done`);
      for (const key of [
        "ui.rail.menu.add",
        "ui.rail.menu.remove",
        "ui.toolbar.added",
        "ui.toolbar.removed",
      ])
        assert.ok(messages[key], `${lang} ${key}`);
    }
  });
});

describe("the checked items", () => {
  test("Show toolbar is on unless the toolbar is hidden", () => {
    assert.equal(CHECKED["view.toolbar"]({}), true);
    assert.equal(CHECKED["view.toolbar"]({ toolbarVisible: true }), true);
    assert.equal(CHECKED["view.toolbar"]({ toolbarVisible: false }), false);
  });

  test("Show text is on in the default mode and off with icons only", () => {
    assert.equal(CHECKED["view.toolbar_labels"]({}), true);
    assert.equal(CHECKED["view.toolbar_labels"]({ toolbarMode: "labels" }), true);
    assert.equal(CHECKED["view.toolbar_labels"]({ toolbarMode: "icons" }), false);
  });

  test("Reset is an action, not a switch", () => {
    assert.equal(CHECKED["view.toolbar_reset"], undefined);
  });
});

describe("otherMode", () => {
  test("switches between icon and text and icon only", () => {
    assert.equal(otherMode("labels"), "icons");
    assert.equal(otherMode("icons"), "labels");
  });

  test("anything else counts as the default, so it goes to icons", () => {
    assert.equal(otherMode("huge"), "icons");
    assert.equal(otherMode(undefined), "icons");
  });
});

describe("the search button at the top of the rail", () => {
  test("runs the command search, a command that exists, and has a label in both languages", async () => {
    const { RAIL_SEARCH } = await import("../toolbar-items.js");
    assert.ok(
      DEFAULT_KEYMAP.find((e) => e.id === RAIL_SEARCH.command),
      RAIL_SEARCH.command,
    );
    for (const lang of ["en", "fi"]) assert.ok(catalog(lang)[RAIL_SEARCH.label], `${lang} label`);
  });

  test("is not one of the layout's commands, so it cannot be moved or removed as a button", async () => {
    const { RAIL_SEARCH } = await import("../toolbar-items.js");
    const { DEFAULT_LAYOUT } = await import("../toolbar-model.js");
    assert.ok(!DEFAULT_LAYOUT.includes(RAIL_SEARCH.command));
  });
});
