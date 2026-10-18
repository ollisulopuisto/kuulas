import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  describeMoment,
  LEFT_OFF_ID,
  leftOffFlag,
  leftOffHere,
  leftOffOf,
  leftOffRow,
  leftOffText,
} from "../left-off.js";

describe("leftOffOf", () => {
  test("the restored cursor and the time it was saved", () => {
    assert.deepEqual(leftOffOf({ playhead: 4800, saved_at: "2026-10-18T18:58:00Z" }, 10000), {
      frame: 4800,
      savedAt: "2026-10-18T18:58:00Z",
    });
  });
  test("no marker at 0, without a number, or without a record", () => {
    assert.equal(leftOffOf({ playhead: 0 }, 10000), null);
    assert.equal(leftOffOf({ playhead: "x" }, 10000), null);
    assert.equal(leftOffOf({}, 10000), null);
    assert.equal(leftOffOf(null, 10000), null);
  });
  test("a position past the end of the edit is clamped to the end", () => {
    assert.equal(leftOffOf({ playhead: 99999 }, 10000).frame, 10000);
  });
  test("a clamp that lands on 0 (an empty edit) is no marker", () => {
    assert.equal(leftOffOf({ playhead: 500 }, 0), null);
  });
  test("a missing saved_at is kept as null", () => {
    assert.equal(leftOffOf({ playhead: 5 }, 10).savedAt, null);
  });
});

describe("leftOffHere", () => {
  test("the playhead now, stamped with the time", () => {
    const now = new Date("2026-10-18T19:00:00Z");
    assert.deepEqual(leftOffHere(777, now), { frame: 777, savedAt: "2026-10-18T19:00:00Z" });
  });
  test("nothing at 0", () => {
    assert.equal(leftOffHere(0, new Date()), null);
  });
});

describe("describeMoment", () => {
  const iso = "2026-10-18T18:58:00Z"; // 21.58 in Helsinki (UTC+3 until 25 Oct)
  test("English: weekday, day, month, time with a dot, in the given zone", () => {
    assert.equal(
      describeMoment(iso, { language: "en", timeZone: "Europe/Helsinki" }),
      "Sun 18 Oct, 21.58",
    );
  });
  test("Finnish uses the Finnish weekday and month", () => {
    const text = describeMoment(iso, { language: "fi", timeZone: "Europe/Helsinki" });
    assert.match(text, /^su 18\.10\./);
    assert.match(text, /21\.58$/);
  });
  test("the zone is the viewer's: UTC shows UTC", () => {
    assert.match(describeMoment(iso, { language: "en", timeZone: "UTC" }), /18\.58$/);
  });
  test("an unreadable or missing time gives an empty string", () => {
    assert.equal(describeMoment(null, { language: "en" }), "");
    assert.equal(describeMoment("not a date", { language: "en" }), "");
  });
});

describe("leftOffText", () => {
  const env = {
    t: (key, params) => `${key} ${JSON.stringify(params)}`,
    clock: (seconds) => `${seconds}s`,
    language: "en",
    timeZone: "Europe/Helsinki",
  };
  test("notice and row carry the position and the moment", () => {
    const leftOff = { frame: 96000, savedAt: "2026-10-18T18:58:00Z" };
    assert.equal(
      leftOffText(leftOff, 48000, env, "notice"),
      'ui.resume.notice {"position":"2s","moment":"Sun 18 Oct, 21.58"}',
    );
    assert.match(leftOffText(leftOff, 48000, env, "row"), /^ui\.resume\.row /);
  });
  test("without a saved time the short text is used", () => {
    assert.equal(
      leftOffText({ frame: 48000, savedAt: null }, 48000, env, "notice"),
      'ui.resume.notice_short {"position":"1s"}',
    );
  });
});

describe("leftOffRow", () => {
  test("a pinned row for the Markers tab", () => {
    assert.deepEqual(leftOffRow({ frame: 96000, savedAt: "x" }, 48000), {
      id: LEFT_OFF_ID,
      frame: 96000,
      seconds: 2,
      savedAt: "x",
    });
  });
  test("none without a left-off position", () => {
    assert.equal(leftOffRow(null, 48000), null);
  });
});

describe("leftOffFlag", () => {
  const view = { scroll: 1000, zoom: 10, width: 500 };
  test("its x on the ruler", () => {
    assert.deepEqual(leftOffFlag({ frame: 2000 }, view), { x: 100 });
  });
  test("not drawn when it is off screen", () => {
    assert.equal(leftOffFlag({ frame: 100 }, view), null);
    assert.equal(leftOffFlag({ frame: 1000 + 10 * 600 }, view), null);
  });
  test("none without a left-off position", () => {
    assert.equal(leftOffFlag(null, view), null);
  });
});
