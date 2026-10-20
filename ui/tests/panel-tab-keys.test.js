// Alt+1 to Alt+5 switch the side-panel tabs (owner, 2026-10-20). Alt+digit is safe on a Finnish
// keyboard (no AltGr, no Shift+digit) and matches by key position (Digit1..Digit5).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { registerAppCommands, sideTabFor } from "../app-commands.js";
import { createRegistry } from "../commands.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { matchesCombo, parseCombo } from "../keys.js";
import { MENU, menuTargets } from "../menu-model.js";

const ORDER = ["inspector", "candidates", "clipboard", "markers", "history"];
const locales = fileURLToPath(new URL("../../src/kuulas/locales/", import.meta.url));
const catalog = (lang) => JSON.parse(readFileSync(`${locales}${lang}.json`, "utf8"));

describe("side-panel tab keys", () => {
  test("each command names one tab, in the tab row's order", () => {
    assert.deepEqual(
      ORDER.map((tab) => sideTabFor(`panel.show_${tab}`)),
      ORDER,
    );
    assert.equal(sideTabFor("panel.next"), null);
  });

  test("they are global, on Alt + digit, and in the View menu", () => {
    const view = menuTargets(MENU.filter((m) => m.id === "view"));
    ORDER.forEach((tab, i) => {
      const entry = DEFAULT_KEYMAP.find((e) => e.id === `panel.show_${tab}`);
      assert.ok(entry, tab);
      assert.equal(entry.context, "global");
      assert.equal(entry.keys.mac, `Alt+${i + 1}`);
      assert.equal(entry.keys.other, `Alt+${i + 1}`);
      assert.ok(view.includes(entry.id), `${entry.id} in View`);
    });
  });

  test("running a command asks the app to show that tab", () => {
    const calls = [];
    const registry = createRegistry();
    const actions = new Proxy(
      {},
      {
        get:
          (_t, name) =>
          (...a) =>
            calls.push([name, ...a]),
      },
    );
    registerAppCommands(registry, { actions, app: { getState: () => ({}), patch() {} } });
    registry.run("panel.show_markers", null, {});
    assert.deepEqual(calls, [["showSideTab", "markers"]]);
  });

  test("Alt+digit matches by key position, not the character Option types", () => {
    const parsed = parseCombo("Alt+4");
    assert.equal(parsed.code, "Digit4");
    const event = {
      code: "Digit4",
      key: "¢",
      altKey: true,
      shiftKey: false,
      ctrlKey: false,
      metaKey: false,
    };
    assert.equal(matchesCombo(event, parsed, "mac"), true);
  });

  test("labels and hints are in both catalogs", () => {
    for (const lang of ["en", "fi"]) {
      const messages = catalog(lang);
      for (const tab of ORDER) {
        assert.ok(messages[`cmd.panel.show_${tab}`], `${lang} label ${tab}`);
        assert.ok(messages[`cmd.panel.show_${tab}.hint`], `${lang} hint ${tab}`);
      }
      assert.ok(messages["menu.side_panels"], `${lang} menu.side_panels`);
    }
  });
});
