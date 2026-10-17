// The default keymap is data. These tests are the WP5 collision test and the
// owner's key decisions (18.10.2026), so a change to either is a visible diff.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { CONTEXTS, DEFAULT_KEYMAP, STATUS_HINTS } from "../keymap-default.js";
import { findCollisions, resolveKeymap } from "../keymap-config.js";
import { parseCombo } from "../keys.js";

const locales = fileURLToPath(new URL("../../src/kuulas/locales/", import.meta.url));
const catalog = (lang) => JSON.parse(readFileSync(`${locales}${lang}.json`, "utf8"));
const asList = (value) => (value === null || value === undefined ? [] : [value].flat());
const keysOf = (id, platform = "other") =>
  asList(DEFAULT_KEYMAP.find((entry) => entry.id === id)?.keys[platform]);

describe("the data", () => {
  test("one entry per command id, each with keys, a context and a label", () => {
    const ids = DEFAULT_KEYMAP.map((entry) => entry.id);
    assert.equal(new Set(ids).size, ids.length);
    for (const entry of DEFAULT_KEYMAP) {
      assert.ok(CONTEXTS.includes(entry.context), `${entry.id}: context ${entry.context}`);
      assert.ok("mac" in entry.keys && "other" in entry.keys, `${entry.id}: both platforms`);
      assert.match(entry.labelKey, /^cmd\./);
    }
  });

  test("every combo parses", () => {
    for (const entry of DEFAULT_KEYMAP) {
      for (const platform of ["mac", "other"]) {
        for (const combo of asList(entry.keys[platform])) {
          assert.notEqual(parseCombo(combo), null, `${entry.id}: ${combo}`);
        }
      }
    }
  });

  test("every label is in both catalogs", () => {
    for (const lang of ["en", "fi"]) {
      const messages = catalog(lang);
      for (const entry of DEFAULT_KEYMAP) {
        assert.ok(messages[entry.labelKey], `${lang}: ${entry.labelKey}`);
      }
      for (const hints of Object.values(STATUS_HINTS)) {
        for (const hint of hints) assert.ok(messages[hint.hintKey], `${lang}: ${hint.hintKey}`);
      }
    }
  });

  test("status-bar hints name commands that exist", () => {
    const ids = new Set(DEFAULT_KEYMAP.map((entry) => entry.id));
    for (const hints of Object.values(STATUS_HINTS)) {
      for (const hint of hints) assert.ok(ids.has(hint.id), hint.id);
    }
  });
});

describe("the WP5 collision test", () => {
  for (const platform of ["mac", "other"]) {
    test(`no two default commands share a key in one context (${platform})`, () => {
      const collisions = findCollisions(resolveKeymap(DEFAULT_KEYMAP, {}, platform));
      assert.deepEqual(collisions, []);
    });
  }
});

describe("the owner's decisions", () => {
  test("Backspace is Delete, X is Cut, Mod+C copies", () => {
    assert.ok(keysOf("edit.delete").includes("Backspace"));
    assert.ok(keysOf("edit.cut").includes("X"));
    assert.deepEqual(keysOf("edit.copy"), ["Mod+C"]);
  });

  test("Spot is Mod+J, find is Mod+F, fade is G, import is Mod+I", () => {
    assert.deepEqual(keysOf("spot"), ["Mod+J"]);
    assert.deepEqual(keysOf("transcript.find"), ["Mod+F"]);
    assert.deepEqual(keysOf("clip.fade"), ["G"]);
    assert.deepEqual(keysOf("app.import"), ["Mod+I"]);
  });

  test("candidates use the physical brackets, K rejects, F2 renames", () => {
    assert.deepEqual(keysOf("candidate.next"), ["]"]);
    assert.deepEqual(keysOf("candidate.previous"), ["["]);
    assert.deepEqual(keysOf("candidate.reject"), ["K"]);
    assert.deepEqual(keysOf("rename"), ["F2"]);
  });

  test("buses collapse on Alt+Mod+Left/Right", () => {
    assert.deepEqual(keysOf("bus.collapse"), ["Alt+Mod+ArrowLeft"]);
    assert.deepEqual(keysOf("bus.expand"), ["Alt+Mod+ArrowRight"]);
  });

  test("the keys the app already had are still in the data", () => {
    assert.deepEqual(keysOf("transport.play"), ["Space"]);
    assert.deepEqual(keysOf("nav.home"), ["Escape"]);
    assert.deepEqual(keysOf("panel.next"), ["F6"]);
    assert.deepEqual(keysOf("panel.previous"), ["Shift+F6"]);
    assert.deepEqual(keysOf("view.toggle"), ["Z"]);
    assert.deepEqual(keysOf("view.fit"), ["Shift+Z"]);
    assert.deepEqual(keysOf("view.back"), ["Alt+Z"]);
    assert.deepEqual(keysOf("view.forward"), ["Shift+Alt+Z"]);
    assert.ok(keysOf("view.zoom_in").includes("="));
    assert.deepEqual(keysOf("view.zoom_out"), ["-"]);
    assert.deepEqual(keysOf("palette.open"), ["Mod+K"]);
    assert.deepEqual(keysOf("help.keys"), ["?"]);
  });

  test("parked items are not bound", () => {
    const ids = DEFAULT_KEYMAP.map((entry) => entry.id).join(" ");
    assert.doesNotMatch(ids, /compare|lift|clean|clipboard_history|close_gap_all/);
    for (const entry of DEFAULT_KEYMAP) {
      for (const combo of [entry.keys.mac, entry.keys.other].flatMap(asList)) {
        assert.notEqual(combo, "Alt+X", entry.id);
        assert.notEqual(combo, "`", entry.id);
      }
    }
  });

  test("the palette and keymap file commands exist, with no key", () => {
    for (const id of ["keymap.import", "keymap.export", "keymap.reset"]) {
      assert.deepEqual(keysOf(id), [], id);
    }
  });
});
