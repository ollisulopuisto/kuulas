// The Preferences dialog (Cmd+,) as data: which settings it gathers and how a change is applied
// through the setters that already exist (no storage of its own).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  applyField,
  currentValues,
  PREFERENCE_FIELDS,
  PREFERENCE_LINKS,
} from "../preferences-model.js";

const catalog = (lang) =>
  JSON.parse(
    readFileSync(
      fileURLToPath(new URL(`../../src/kuulas/locales/${lang}.json`, import.meta.url)),
      "utf8",
    ),
  );

function recorder() {
  const calls = [];
  const setters = new Proxy(
    {},
    {
      get:
        (_t, name) =>
        (...args) =>
          calls.push([name, ...args]),
    },
  );
  return { calls, setters };
}

describe("the fields", () => {
  test("gather the owner's list, once each", () => {
    assert.deepEqual(
      PREFERENCE_FIELDS.map((field) => field.id),
      ["language", "stopMode", "preroll", "confirmSync", "clipboardLimit", "fast"],
    );
  });

  test("choices have options, a range has bounds, every text exists in both catalogs", () => {
    for (const lang of ["en", "fi"]) {
      const words = catalog(lang);
      for (const field of PREFERENCE_FIELDS) {
        assert.ok(words[field.labelKey], `${lang}: ${field.labelKey}`);
        for (const option of field.options ?? []) {
          assert.ok(words[option.labelKey], `${lang}: ${option.labelKey}`);
        }
      }
      for (const link of PREFERENCE_LINKS)
        assert.ok(words[link.labelKey], `${lang}: ${link.labelKey}`);
    }
    for (const field of PREFERENCE_FIELDS.filter((f) => f.kind === "choice")) {
      assert.ok(field.options.length >= 2, field.id);
    }
    const range = PREFERENCE_FIELDS.find((f) => f.kind === "range");
    assert.ok(range.min < range.max && range.step > 0);
  });

  test("the links open the Colab settings, the automixer and the key map", () => {
    assert.deepEqual(
      PREFERENCE_LINKS.map((link) => link.command),
      ["app.colab_settings", "export.automix", "help.keys"],
    );
  });
});

describe("currentValues", () => {
  test("reads the state the existing preferences keep", () => {
    const values = currentValues(
      { languageChoice: "fi", confirmSync: false, clipboardLimit: true, fast: { fast: 1.35 } },
      { stopMode: "hold", preroll: 30 },
    );
    assert.deepEqual(values, {
      language: "fi",
      stopMode: "hold",
      preroll: "30",
      confirmSync: false,
      clipboardLimit: true,
      fast: 1.35,
    });
  });

  test("defaults when nothing is set", () => {
    const values = currentValues({}, {});
    assert.equal(values.language, "auto");
    assert.equal(values.confirmSync, true);
    assert.equal(values.clipboardLimit, true);
    assert.equal(values.stopMode, "two_step");
  });
});

describe("applyField", () => {
  test("calls the matching setter with a typed value", () => {
    const { calls, setters } = recorder();
    const current = currentValues({}, { stopMode: "two_step", preroll: 60 });
    assert.equal(applyField("language", "fi", current, setters), true);
    assert.equal(applyField("stopMode", "hold", current, setters), true);
    assert.equal(applyField("preroll", "30", current, setters), true);
    assert.equal(applyField("confirmSync", false, current, setters), true);
    assert.equal(applyField("clipboardLimit", false, current, setters), true);
    assert.equal(applyField("fast", "1.35", current, setters), true);
    assert.deepEqual(calls, [
      ["language", "fi"],
      ["stopMode", "hold"],
      ["preroll", 30],
      ["confirmSync", false],
      ["clipboardLimit", false],
      ["fast", 1.35],
    ]);
  });

  test("an unchanged, unknown or invalid value calls nothing", () => {
    const { calls, setters } = recorder();
    const current = currentValues({}, { stopMode: "two_step", preroll: 60 });
    assert.equal(applyField("language", "auto", current, setters), false);
    assert.equal(applyField("language", "sv", current, setters), false);
    assert.equal(applyField("stopMode", "bogus", current, setters), false);
    assert.equal(applyField("preroll", "45", current, setters), false);
    assert.equal(applyField("fast", "abc", current, setters), false);
    assert.equal(applyField("nope", "x", current, setters), false);
    assert.deepEqual(calls, []);
  });
});
