// Locate media… and Send a copy…: the pure parts of the two dialogs.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  choiceRows,
  DEFAULT_MEDIA_CHOICE,
  folderOf,
  locateSummary,
  MEDIA_CHOICES,
  missingNotice,
  sendCopyRequest,
  sizeText,
} from "../media-copy-model.js";

describe("missingNotice", () => {
  test("nothing missing, no notice", () => {
    assert.equal(missingNotice([]), null);
    assert.equal(missingNotice(undefined), null);
  });
  test("counts the missing files", () => {
    assert.deepEqual(missingNotice(["a", "b"]), { key: "ui.locate.notice", values: { count: 2 } });
  });
});

describe("folderOf", () => {
  test("trims, and an empty text is no folder", () => {
    assert.equal(folderOf("  /Volumes/Raid/Kapina "), "/Volumes/Raid/Kapina");
    assert.equal(folderOf("   "), null);
    assert.equal(folderOf(undefined), null);
  });
});

describe("locateSummary", () => {
  test("found of all that were being looked for", () => {
    const report = { found: [{ id: "a" }], still_missing: [{ id: "b" }, { id: "c" }], partial: [] };
    assert.deepEqual(locateSummary(report), {
      key: "ui.locate.summary",
      values: { found: 1, total: 3, left: 2 },
    });
  });
  test("a clean report finds all", () => {
    const report = { found: [{ id: "a" }], still_missing: [], partial: [] };
    assert.deepEqual(locateSummary(report).values, { found: 1, total: 1, left: 0 });
  });
});

describe("sizeText", () => {
  test("megabytes, then gigabytes with one decimal", () => {
    assert.equal(sizeText(0), "0 MB");
    assert.equal(sizeText(400_000), "1 MB");
    assert.equal(sizeText(250_000_000), "250 MB");
    assert.equal(sizeText(1_540_000_000), "1.5 GB");
  });
});

describe("the media choices", () => {
  test("none, used, all; the used parts are the default", () => {
    assert.deepEqual(MEDIA_CHOICES, ["none", "used", "all"]);
    assert.equal(DEFAULT_MEDIA_CHOICE, "used");
  });
  test("a row per choice with the size the server estimated", () => {
    const plan = {
      none: { bytes: 0 },
      used: { bytes: 30_000_000 },
      all: { bytes: 2_000_000_000 },
      handle_seconds: 2,
    };
    assert.deepEqual(
      choiceRows(plan).map((row) => [row.id, row.size]),
      [
        ["none", "0 MB"],
        ["used", "30 MB"],
        ["all", "2.0 GB"],
      ],
    );
  });
  test("without a plan the rows have no size", () => {
    assert.deepEqual(
      choiceRows(null).map((row) => row.size),
      [null, null, null],
    );
  });
});

describe("sendCopyRequest", () => {
  test("needs a folder", () => {
    assert.deepEqual(sendCopyRequest({ folder: " ", media: "used" }), {
      ok: false,
      key: "ui.send_copy.pick_folder",
    });
  });
  test("the body for POST /api/send-copy", () => {
    assert.deepEqual(sendCopyRequest({ folder: " /tmp/out ", media: "all" }), {
      ok: true,
      body: { folder: "/tmp/out", media: "all" },
    });
  });
  test("an unknown choice falls back to the default", () => {
    assert.equal(sendCopyRequest({ folder: "/x", media: "bogus" }).body.media, "used");
  });
});
