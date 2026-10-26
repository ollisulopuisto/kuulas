// The View switches of the toolbar (WP86): show it, show text on its buttons, reset it.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { CHECKED, MENU, menuTargets } from "../menu-model.js";
import { otherMode } from "../toolbar-prefs.js";

const IDS = ["view.toolbar", "view.toolbar_labels", "view.toolbar_reset"];
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
