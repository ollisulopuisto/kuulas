import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { dragHasFiles, summariseImport } from "../importing.js";

describe("import", () => {
  test("a clean import counts the files", () => {
    const out = summariseImport([
      { path: "/u/a.wav", ok: true, error: null, warnings: [] },
      { path: "/u/b.wav", ok: true, error: null, warnings: [] },
    ]);
    assert.deepEqual(out, { imported: 2, failures: [], warnings: [] });
  });

  test("a bad file is listed with the server's text and the rest still counts", () => {
    const out = summariseImport([
      { path: "/u/a.wav", ok: true, error: null, warnings: [{ text: "Sample rate converted" }] },
      { path: "/u/bad.wav", ok: false, error: { text: "Cannot read this file" }, warnings: [] },
    ]);
    assert.equal(out.imported, 1);
    assert.deepEqual(out.failures, [{ name: "bad.wav", text: "Cannot read this file" }]);
    assert.deepEqual(out.warnings, [{ name: "a.wav", text: "Sample rate converted" }]);
  });

  test("a missing report counts as nothing", () => {
    assert.deepEqual(summariseImport(undefined), { imported: 0, failures: [], warnings: [] });
  });

  test("only a drag that carries files shows the drop target", () => {
    assert.equal(dragHasFiles({ types: ["Files"] }), true);
    assert.equal(dragHasFiles({ types: ["text/plain"] }), false);
    assert.equal(dragHasFiles(null), false);
  });
});
