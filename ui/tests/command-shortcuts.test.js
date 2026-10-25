import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { applyCommandShortcuts } from "../command-shortcuts.js";
import { formatShortcut, setCatalogs, setLanguageNow, setShortcutResolver, t } from "../i18n.js";
import { resolveKeymap } from "../keymap-config.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";

test("message tokens resolve at render time, including remaps, slots and unbound commands", () => {
  setCatalogs({
    en: {
      hint: "Use {key:marker.add}.",
      cart: "Use {key:clipboard.cart_assign_{slot}}.",
      "cmd.marker.add": "Add marker",
    },
  });
  setLanguageNow("en");
  let binding = "Mod+Enter";
  setShortcutResolver(() => binding);
  assert.equal(t("hint"), `Use ${formatShortcut("Mod+Enter")}.`);
  binding = "F8";
  assert.equal(t("hint"), "Use F8.");
  setShortcutResolver((id) => (id === "clipboard.cart_assign_3" ? "F3" : null));
  assert.equal(t("cart", { slot: 3 }), "Use F3.");
  assert.equal(t("hint"), "Use Add marker.");
  setShortcutResolver(null);
});

test("command buttons expose current platform bindings and clear removed bindings", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  assert.doesNotMatch(html, /aria-keyshortcuts=/);
  const ids = [
    "play",
    "loop",
    "view-toggle",
    "scope-chip",
    "help-button",
    "zoom-out",
    "zoom-in",
    "fit",
  ];
  for (const platform of ["mac", "other"]) {
    const entries = resolveKeymap(
      DEFAULT_KEYMAP,
      { "view.toggle": "F8", "view.zoom_in": null },
      platform,
    );
    const nodes = ids.map((id) => {
      const tag = html.match(new RegExp(`<button[^>]*id="${id}"[^>]*>`))?.[0];
      const command = tag?.match(/data-cmd="([^"]+)"/)?.[1];
      assert.ok(command, id);
      return {
        dataset: { cmd: command },
        attrs: {},
        setAttribute(k, v) {
          this.attrs[k] = v;
        },
      };
    });
    applyCommandShortcuts(
      { querySelectorAll: (selector) => (selector === "[data-cmd]" ? nodes : []) },
      entries,
      platform,
    );
    for (const node of nodes) {
      const entry = entries.find((e) => e.id === node.dataset.cmd);
      const raw = entry.raw;
      const combos = raw ? (Array.isArray(raw) ? raw : [raw]) : [];
      assert.equal(
        node.attrs["aria-keyshortcuts"],
        combos.map((c) => c.replace(/\bMod\b/, platform === "mac" ? "Meta" : "Control")).join(" "),
      );
    }
  }
});

test("all catalog command tokens name real commands and render in both languages when unbound", () => {
  const catalogs = Object.fromEntries(
    ["en", "fi"].map((lang) => [
      lang,
      JSON.parse(readFileSync(new URL(`../../src/kuulas/locales/${lang}.json`, import.meta.url))),
    ]),
  );
  setCatalogs(catalogs);
  const commands = new Set(DEFAULT_KEYMAP.map((entry) => entry.id));
  for (const lang of ["en", "fi"]) {
    setLanguageNow(lang);
    for (const [key, value] of Object.entries(catalogs[lang])) {
      if (!JSON.stringify(value).includes("{key:")) continue;
      for (const binding of [null, "F8"]) {
        setShortcutResolver((id) => {
          assert.ok(commands.has(id), `${key}: ${id}`);
          assert.ok(catalogs[lang][`cmd.${id}`], id);
          return binding;
        });
        for (const count of [1, 2]) {
          const rendered = t(key, { count, slot: 3, name: "test" });
          assert.doesNotMatch(rendered, /\{key:|cmd\./, key);
          if (binding) assert.match(rendered, /F8/, key);
        }
      }
    }
  }
  setShortcutResolver(null);
  setLanguageNow("en");
});
