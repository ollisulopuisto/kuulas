import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { parseOffset, parseTime } from "../time-parse.js";

describe("parseTime", () => {
  test("parses plain seconds with dot or comma", () => {
    assert.equal(parseTime("83.2"), 83.2);
    assert.equal(parseTime("83,2"), 83.2);
    assert.equal(parseTime("0"), 0);
    assert.equal(parseTime("0.0"), 0);
    assert.equal(parseTime("120"), 120);
    assert.equal(parseTime("  83.2  "), 83.2);
  });

  test("parses m:ss and m:ss.sss", () => {
    assert.equal(parseTime("1:23"), 83);
    assert.equal(parseTime("1:23.5"), 83.5);
    assert.equal(parseTime("1:23,5"), 83.5);
    assert.equal(parseTime("0:00"), 0);
    assert.equal(parseTime("0:05.100"), 5.1);
    assert.equal(parseTime("100:30"), 6030);
  });

  test("parses h:mm:ss and h:mm:ss.sss", () => {
    assert.equal(parseTime("1:02:03"), 3723);
    assert.equal(parseTime("1:02:03.250"), 3723.25);
    assert.equal(parseTime("1:02:03,250"), 3723.25);
    assert.equal(parseTime("0:00:00"), 0);
    assert.equal(parseTime("2:30:15.5"), 9015.5);
  });

  test("rejects leading minus or plus", () => {
    assert.equal(parseTime("-5"), null);
    assert.equal(parseTime("-1:23"), null);
    assert.equal(parseTime("+5"), null);
    assert.equal(parseTime("+1:23"), null);
  });

  test("rejects invalid characters, empty, or wrong part counts", () => {
    assert.equal(parseTime(""), null);
    assert.equal(parseTime("   "), null);
    assert.equal(parseTime(null), null);
    assert.equal(parseTime(undefined), null);
    assert.equal(parseTime("abc"), null);
    assert.equal(parseTime("1:23a"), null);
    assert.equal(parseTime("1:2:3:4"), null);
    assert.equal(parseTime(":"), null);
    assert.equal(parseTime("1:"), null);
    assert.equal(parseTime(":23"), null);
  });

  test("rejects minutes or seconds >= 60 when larger unit is present", () => {
    assert.equal(parseTime("1:60"), null);
    assert.equal(parseTime("1:75"), null);
    assert.equal(parseTime("1:60:00"), null);
    assert.equal(parseTime("1:02:60"), null);
    assert.equal(parseTime("1:65:20"), null);
  });
});

describe("parseOffset", () => {
  test("parses offset with leading plus", () => {
    assert.deepEqual(parseOffset("+83.2"), { sign: 1, seconds: 83.2 });
    assert.deepEqual(parseOffset("+1:23"), { sign: 1, seconds: 83 });
    assert.deepEqual(parseOffset(" + 1:23 "), { sign: 1, seconds: 83 });
  });

  test("parses offset with leading minus", () => {
    assert.deepEqual(parseOffset("-83.2"), { sign: -1, seconds: 83.2 });
    assert.deepEqual(parseOffset("-1:02:03.250"), { sign: -1, seconds: 3723.25 });
    assert.deepEqual(parseOffset(" - 83,2 "), { sign: -1, seconds: 83.2 });
  });

  test("parses offset without sign (sign 0)", () => {
    assert.deepEqual(parseOffset("83.2"), { sign: 0, seconds: 83.2 });
    assert.deepEqual(parseOffset("1:23"), { sign: 0, seconds: 83 });
  });

  test("returns null for invalid offsets or bare signs", () => {
    assert.equal(parseOffset("+"), null);
    assert.equal(parseOffset("-"), null);
    assert.equal(parseOffset(""), null);
    assert.equal(parseOffset(null), null);
    assert.equal(parseOffset("+abc"), null);
    assert.equal(parseOffset("-1:60"), null);
    assert.equal(parseOffset("++1:23"), null);
  });
});
