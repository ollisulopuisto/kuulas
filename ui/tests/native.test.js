import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { nativeBridge } from "../importing.js";

describe("native bridge detection", () => {
  test("a plain browser has no bridge", () => {
    assert.equal(nativeBridge({}), null);
    assert.equal(nativeBridge(undefined), null);
    assert.equal(nativeBridge({ pywebview: {} }), null);
  });

  test("pywebview before its api is injected is not a bridge yet", () => {
    assert.equal(nativeBridge({ pywebview: { api: {} } }), null);
  });

  test("the injected api is returned once it can pick media", () => {
    const api = { pick_media: () => Promise.resolve([]) };
    assert.equal(nativeBridge({ pywebview: { api } }), api);
  });
});
