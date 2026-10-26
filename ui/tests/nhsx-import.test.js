// File > Import Hindenburg session… : what the page asks for and what it says afterwards.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { MENU, menuTargets } from "../menu-model.js";
import { nhsxRequest, nhsxResult } from "../nhsx-import.js";

const catalog = (lang) =>
  JSON.parse(
    readFileSync(
      fileURLToPath(new URL(`../../src/kuulas/locales/${lang}.json`, import.meta.url)),
      "utf8",
    ),
  );

describe("the request", () => {
  test("an absolute path to a .nhsx file goes through, trimmed", () => {
    assert.deepEqual(nhsxRequest("  /Users/o/Show/Show.nhsx "), {
      ok: true,
      body: { path: "/Users/o/Show/Show.nhsx" },
    });
    assert.equal(nhsxRequest("C:\\Shows\\Show.NHSX").ok, true, "any case, Windows paths too");
  });

  test("quotes from a copied path are dropped", () => {
    assert.equal(nhsxRequest('"/a/b.nhsx"').body.path, "/a/b.nhsx");
    assert.equal(nhsxRequest("'/a/b.nhsx'").body.path, "/a/b.nhsx");
  });

  test("anything else is refused with a message key", () => {
    for (const bad of ["", "   ", "Show.nhsx", "~/Show.nhsx", "/a/../b.nhsx", "/a/b.wav", "/a/b"]) {
      const r = nhsxRequest(bad);
      assert.equal(r.ok, false, bad);
      assert.ok(r.key.startsWith("ui.nhsx."), bad);
    }
    assert.equal(nhsxRequest(null).ok, false);
  });
});

describe("the result", () => {
  test("recordings in, nothing missing: a plain done", () => {
    assert.deepEqual(nhsxResult({ imported: 4, failures: [], warnings: [] }), {
      key: "ui.nhsx.done",
      values: { count: 4 },
      kind: "ok",
    });
  });

  test("some recordings missing: says how many, as a warning", () => {
    const r = nhsxResult({
      imported: 3,
      failures: [{ name: "a.wav" }, { name: "b.wav" }],
      warnings: [],
    });
    assert.equal(r.key, "ui.nhsx.partial");
    assert.deepEqual(r.values, { count: 3, missing: 2 });
    assert.equal(r.kind, "warn");
  });

  test("nothing came in: an error", () => {
    assert.equal(nhsxResult({ imported: 0, failures: [], warnings: [] }).kind, "error");
    assert.equal(
      nhsxResult({ imported: 0, failures: [{ name: "a.wav" }], warnings: [] }).kind,
      "error",
    );
  });
});

describe("the command", () => {
  test("is in the keymap without a key, in the File menu, and named in both languages", () => {
    const entry = DEFAULT_KEYMAP.find((e) => e.id === "app.import_nhsx");
    assert.ok(entry);
    assert.deepEqual(entry.keys, { mac: null, other: null });
    const file = MENU.find((menu) => menu.id === "file");
    assert.ok(menuTargets([file]).includes("app.import_nhsx"));
    for (const lang of ["en", "fi"]) {
      const messages = catalog(lang);
      for (const key of [
        "cmd.app.import_nhsx",
        "cmd.app.import_nhsx.hint",
        "ui.nhsx.title",
        "ui.nhsx.path",
        "ui.nhsx.note",
        "ui.nhsx.need_path",
        "ui.nhsx.need_nhsx",
        "ui.nhsx.go",
        "ui.nhsx.done",
        "ui.nhsx.partial",
        "ui.nhsx.nothing",
      ])
        assert.ok(messages[key], `${lang} ${key}`);
    }
  });
});
