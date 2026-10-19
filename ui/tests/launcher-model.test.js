import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  folderName,
  formatDuration,
  formatSize,
  nextRow,
  relativeTime,
  rowModel,
} from "../launcher-model.js";

const NOW = new Date(2026, 9, 19, 15, 0, 0).getTime();
const ago = (ms) => NOW - ms;
const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

describe("relativeTime", () => {
  test("under a minute is now", () => {
    assert.equal(relativeTime(ago(10_000), NOW, "en"), "now");
    assert.equal(relativeTime(ago(10_000), NOW, "fi"), "nyt");
  });
  test("minutes", () => {
    assert.equal(relativeTime(ago(2 * MIN), NOW, "en"), "2 minutes ago");
    assert.equal(relativeTime(ago(2 * MIN), NOW, "fi"), "2 minuuttia sitten");
    assert.equal(relativeTime(ago(59 * MIN), NOW, "en"), "59 minutes ago");
  });
  test("hours", () => {
    assert.equal(relativeTime(ago(3 * HOUR + 20 * MIN), NOW, "en"), "3 hours ago");
    assert.equal(relativeTime(ago(5 * HOUR), NOW, "fi"), "5 tuntia sitten");
  });
  test("yesterday is a calendar day, not 24 hours", () => {
    const lateLastNight = new Date(2026, 9, 18, 23, 30).getTime();
    assert.equal(relativeTime(lateLastNight, NOW, "en"), "yesterday");
    assert.equal(relativeTime(ago(30 * HOUR), NOW, "fi"), "eilen");
  });
  test("days, weeks, months, years", () => {
    assert.equal(relativeTime(ago(3 * DAY), NOW, "en"), "3 days ago");
    assert.equal(relativeTime(ago(14 * DAY), NOW, "en"), "2 weeks ago");
    assert.equal(relativeTime(ago(70 * DAY), NOW, "en"), "2 months ago");
    assert.equal(relativeTime(ago(800 * DAY), NOW, "en"), "2 years ago");
  });
  test("a clock slightly in the future is still now", () => {
    assert.equal(relativeTime(NOW + 5_000, NOW, "en"), "now");
  });
  test("an unreadable time is null", () => {
    assert.equal(relativeTime(Number.NaN, NOW, "en"), null);
    assert.equal(relativeTime(null, NOW, "en"), null);
  });
});

describe("formatSize", () => {
  test("bytes to GB, one decimal under 10", () => {
    assert.equal(formatSize(0, "en"), "0 B");
    assert.equal(formatSize(900, "en"), "900 B");
    assert.equal(formatSize(1536, "en"), "1.5 kB");
    assert.equal(formatSize(5 * 1024 * 1024, "en"), "5.0 MB");
    assert.equal(formatSize(250 * 1024 * 1024, "en"), "250 MB");
    assert.equal(formatSize(3.5 * 1024 ** 3, "en"), "3.5 GB");
  });
  test("Finnish decimal comma", () => {
    assert.equal(formatSize(1536, "fi"), "1,5 kB");
  });
  test("not a size is null", () => {
    assert.equal(formatSize(undefined, "en"), null);
    assert.equal(formatSize(-1, "en"), null);
  });
});

describe("formatDuration", () => {
  test("m:ss and h:mm:ss", () => {
    assert.equal(formatDuration(0), "0:00");
    assert.equal(formatDuration(61.4), "1:01");
    assert.equal(formatDuration(3725), "1:02:05");
  });
  test("not a duration is null", () => {
    assert.equal(formatDuration(undefined), null);
    assert.equal(formatDuration(-3), null);
  });
});

describe("folderName", () => {
  test("drops the folder and the .kuulas suffix, either slash", () => {
    assert.equal(folderName("/a/b/Show s13e04.kuulas/"), "Show s13e04");
    assert.equal(folderName("C:\\a\\Show.kuulas"), "Show");
    assert.equal(folderName("/a/Plain"), "Plain");
  });
});

const LABELS = {
  opened: "Opened",
  tracks: "Tracks",
  duration: "Duration",
  size: "Size",
  size_tip: "Project folder only; linked media is not counted",
  missing: "Folder not found",
};

describe("rowModel", () => {
  test("a full record gives name, path and four labelled chips", () => {
    const row = rowModel(
      {
        path: "/a/Show.kuulas",
        exists: true,
        opened_utc: new Date(ago(2 * MIN)).toISOString(),
        tracks: 3,
        duration_s: 61,
        size_bytes: 1536,
      },
      NOW,
      "en",
      LABELS,
    );
    assert.equal(row.name, "Show");
    assert.equal(row.path, "/a/Show.kuulas");
    assert.equal(row.missing, false);
    assert.deepEqual(
      row.chips.map((c) => [c.key, c.label, c.text]),
      [
        ["opened", "Opened", "2 minutes ago"],
        ["tracks", "Tracks", "3"],
        ["duration", "Duration", "1:01"],
        ["size", "Size", "1.5 kB"],
      ],
    );
    assert.equal(row.chips[3].title, LABELS.size_tip);
  });
  test("a record without metadata has only the time, or nothing", () => {
    const old = rowModel({ path: "/a/Old.kuulas", exists: true }, NOW, "en", LABELS);
    assert.deepEqual(old.chips, []);
    const timed = rowModel(
      { path: "/a/Old.kuulas", exists: true, opened_utc: new Date(ago(3 * DAY)).toISOString() },
      NOW,
      "en",
      LABELS,
    );
    assert.deepEqual(
      timed.chips.map((c) => c.key),
      ["opened"],
    );
  });
  test("zero tracks and zero length are shown, not hidden", () => {
    const row = rowModel(
      { path: "/a/E.kuulas", exists: true, tracks: 0, duration_s: 0, size_bytes: 0 },
      NOW,
      "en",
      LABELS,
    );
    assert.deepEqual(
      row.chips.map((c) => c.text),
      ["0", "0:00", "0 B"],
    );
  });
  test("a missing folder is marked, with a note, and keeps its old facts", () => {
    const row = rowModel({ path: "/gone/X.kuulas", exists: false, tracks: 2 }, NOW, "en", LABELS);
    assert.equal(row.missing, true);
    assert.equal(row.note, "Folder not found");
    assert.equal(row.chips[0].key, "tracks");
  });
});

describe("nextRow", () => {
  test("arrows move and stop at the ends", () => {
    assert.equal(nextRow(0, "ArrowDown", 3), 1);
    assert.equal(nextRow(2, "ArrowDown", 3), 2);
    assert.equal(nextRow(1, "ArrowUp", 3), 0);
    assert.equal(nextRow(0, "ArrowUp", 3), 0);
  });
  test("Home and End; no row means the first or last", () => {
    assert.equal(nextRow(1, "Home", 3), 0);
    assert.equal(nextRow(1, "End", 3), 2);
    assert.equal(nextRow(-1, "ArrowDown", 3), 0);
    assert.equal(nextRow(-1, "ArrowUp", 3), 2);
  });
  test("other keys and an empty list give null", () => {
    assert.equal(nextRow(1, "a", 3), null);
    assert.equal(nextRow(0, "ArrowDown", 0), null);
  });
});
