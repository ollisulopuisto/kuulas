import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { DEFAULT_TONES, sortStatuses, statusTone } from "../status-tone.js";

describe("DEFAULT_TONES", () => {
  test("defines all expected default tones", () => {
    assert.deepEqual(DEFAULT_TONES, {
      Draft: "neutral",
      "Ready for review": "info",
      "In review": "info",
      "Needs fixes": "warn",
      Reviewed: "ok",
      Approved: "ok",
      Published: "done",
    });
  });
});

describe("statusTone", () => {
  test("every default tone", () => {
    assert.equal(statusTone("Draft"), "neutral");
    assert.equal(statusTone("Ready for review"), "info");
    assert.equal(statusTone("In review"), "info");
    assert.equal(statusTone("Needs fixes"), "warn");
    assert.equal(statusTone("Reviewed"), "ok");
    assert.equal(statusTone("Approved"), "ok");
    assert.equal(statusTone("Published"), "done");
  });

  test("case and spaces", () => {
    assert.equal(statusTone("draft"), "neutral");
    assert.equal(statusTone("  DRAFT  "), "neutral");
    assert.equal(statusTone("READY FOR REVIEW"), "info");
    assert.equal(statusTone("  in review  "), "info");
    assert.equal(statusTone("needs fixes"), "warn");
    assert.equal(statusTone("  REVIEWED  "), "ok");
    assert.equal(statusTone(" approved "), "ok");
    assert.equal(statusTone("published"), "done");
  });

  test("unknown and empty labels return neutral", () => {
    assert.equal(statusTone("Unknown Status"), "neutral");
    assert.equal(statusTone(""), "neutral");
    assert.equal(statusTone("   "), "neutral");
    assert.equal(statusTone(null), "neutral");
    assert.equal(statusTone(undefined), "neutral");
  });

  test("custom tones mapping", () => {
    const custom = { Archived: "warn", Active: "ok" };
    assert.equal(statusTone("archived", custom), "warn");
    assert.equal(statusTone("  Active  ", custom), "ok");
    assert.equal(statusTone("Draft", custom), "neutral");
  });
});

describe("sortStatuses", () => {
  const order = [
    "Draft",
    "Ready for review",
    "In review",
    "Needs fixes",
    "Reviewed",
    "Approved",
    "Published",
  ];

  test("sort order with unknowns", () => {
    const input = ["Published", "Custom A", "Draft", "Custom B", "Needs fixes"];
    assert.deepEqual(sortStatuses(input, order), [
      "Draft",
      "Needs fixes",
      "Published",
      "Custom A",
      "Custom B",
    ]);
  });

  test("sort order is case-insensitive regarding order list", () => {
    const input = ["published", "draft", "NEEDS FIXES"];
    assert.deepEqual(sortStatuses(input, order), ["draft", "NEEDS FIXES", "published"]);
  });

  test("duplicates kept once with the first spelling", () => {
    const input = ["draft", "Draft", "DRAFT", "Approved", "approved", "Custom", "custom"];
    assert.deepEqual(sortStatuses(input, order), ["draft", "Approved", "Custom"]);
  });

  test("an empty list", () => {
    assert.deepEqual(sortStatuses([], order), []);
    assert.deepEqual(sortStatuses(null, order), []);
  });
});
