// File > Open Recent: the menu entries from the start page's recent.json records.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { MAX_RECENT_MENU, recentMenuItems } from "../recent-menu-model.js";

const NOW = Date.parse("2026-10-19T12:00:00Z");
const record = (name, over = {}) => ({
  path: `/Users/me/Podcasts/${name}.kuulas`,
  opened_utc: "2026-10-19T11:00:00Z",
  exists: true,
  ...over,
});

describe("recentMenuItems", () => {
  test("one entry per record, in order: path, name without .kuulas, time", () => {
    const items = recentMenuItems([record("Show 12"), record("Show 11")], { nowMs: NOW });
    assert.deepEqual(
      items.map((item) => [item.path, item.label]),
      [
        ["/Users/me/Podcasts/Show 12.kuulas", "Show 12"],
        ["/Users/me/Podcasts/Show 11.kuulas", "Show 11"],
      ],
    );
    assert.match(items[0].detail, /hour/);
  });

  test("at most ten by default, or max", () => {
    const records = Array.from({ length: 14 }, (_, i) => record(`P${i}`));
    assert.equal(MAX_RECENT_MENU, 10);
    assert.equal(recentMenuItems(records, { nowMs: NOW }).length, 10);
    assert.equal(recentMenuItems(records, { nowMs: NOW, max: 3 }).length, 3);
  });

  test("a folder that is gone is marked missing; a record without the fact counts as there", () => {
    const [gone, there, unknown] = recentMenuItems(
      [record("A", { exists: false }), record("B"), record("C", { exists: undefined })],
      { nowMs: NOW },
    );
    assert.equal(gone.missing, true);
    assert.equal(there.missing, false);
    assert.equal(unknown.missing, false);
  });

  test("a record without a time has no time detail, bare strings are paths", () => {
    const [noTime, bare] = recentMenuItems(
      [record("A", { opened_utc: undefined }), "/x/Bare.kuulas"],
      { nowMs: NOW },
    );
    assert.equal(noTime.detail, "");
    assert.equal(bare.label, "Bare");
    assert.equal(bare.path, "/x/Bare.kuulas");
  });

  test("damage is ignored: not an array, records without a path, repeats of one path", () => {
    assert.deepEqual(recentMenuItems(null, { nowMs: NOW }), []);
    const items = recentMenuItems([null, {}, { path: "" }, record("A"), record("A"), 7], {
      nowMs: NOW,
    });
    assert.equal(items.length, 1);
  });

  test("the time follows the language", () => {
    const [fi] = recentMenuItems([record("A")], { nowMs: NOW, lang: "fi" });
    assert.match(fi.detail, /tunti/);
  });
});
