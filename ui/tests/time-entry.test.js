import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  emptyEntry,
  entryFromDigits,
  entrySeconds,
  entryText,
  isDigits,
  rawText,
  typeKey,
} from "../time-entry.js";

const type = (keys, start = emptyEntry()) =>
  [...keys].reduce((entry, k) => typeKey(entry, k), start);
const shown = (keys, decimal = ",") => entryText(type(keys), decimal);

describe("digits fill from the right", () => {
  test("nothing typed shows a zero timestamp", () => {
    assert.equal(entryText(emptyEntry(), ","), "0:00:00");
  });
  test("1 is one second, 10 is ten seconds", () => {
    assert.equal(shown("1"), "0:00:01");
    assert.equal(shown("10"), "0:00:10");
  });
  test("110 is 1:10, 1234 is 12:34, 10000 is 1:00:00", () => {
    assert.equal(shown("110"), "0:01:10");
    assert.equal(shown("1234"), "0:12:34");
    assert.equal(shown("10000"), "1:00:00");
    assert.equal(entrySeconds(type("110")), 70);
    assert.equal(entrySeconds(type("1234")), 754);
    assert.equal(entrySeconds(type("10000")), 3600);
  });
  test("a field over 59 is shown as typed and added up on the jump", () => {
    assert.equal(shown("99"), "0:00:99");
    assert.equal(entrySeconds(type("99")), 99);
    assert.equal(entrySeconds(type("175")), 135);
  });
  test("leading zeros change nothing and do not use up room", () => {
    assert.equal(shown("0005"), "0:00:05");
    assert.equal(entrySeconds(type("0005")), 5);
  });
  test("the digits are capped, the extra ones are ignored", () => {
    const many = type("123456789012");
    assert.equal(rawText(many), "12345678");
  });
});

describe("a comma or period starts a fraction", () => {
  test("10,5 is 10.5 seconds, digits then fill left to right up to milliseconds", () => {
    assert.equal(shown("10,5"), "0:00:10,5");
    assert.equal(entrySeconds(type("10,5")), 10.5);
    assert.equal(shown("10,1234"), "0:00:10,123");
    assert.equal(entrySeconds(type("10,1234")), 10.123);
  });
  test("the separator follows the language", () => {
    assert.equal(shown("10.5", "."), "0:00:10.5");
    assert.equal(shown("10,5", "."), "0:00:10.5");
  });
  test("a lone separator shows and a second one is ignored", () => {
    assert.equal(shown("7,"), "0:00:07,");
    assert.equal(shown("7,,5"), "0:00:07,5");
  });
  test("a fraction on no whole digits is a fraction of a second", () => {
    assert.equal(entrySeconds(type(",5")), 0.5);
  });
});

describe("Backspace removes the last digit and the rest shifts right", () => {
  test("whole digits", () => {
    const back = typeKey(type("1234"), "Backspace");
    assert.equal(entryText(back, ","), "0:01:23");
    const gone = ["Backspace", "Backspace", "Backspace"].reduce(typeKey, back);
    assert.equal(entryText(gone, ","), "0:00:00");
  });
  test("fraction digits go first, then the separator", () => {
    const entry = type("10,52");
    const one = typeKey(entry, "Backspace");
    assert.equal(entryText(one, ","), "0:00:10,5");
    const two = typeKey(one, "Backspace");
    assert.equal(entryText(two, ","), "0:00:10,");
    const three = typeKey(two, "Backspace");
    assert.equal(entryText(three, ","), "0:00:10");
    assert.equal(entryText(typeKey(three, "Backspace"), ","), "0:00:01");
  });
  test("on an empty entry it does nothing", () => {
    assert.equal(entryText(typeKey(emptyEntry(), "Backspace"), ","), "0:00:00");
  });
});

describe("other keys and pasted digits", () => {
  test("a key that is no digit, separator or Backspace changes nothing", () => {
    const entry = type("12");
    assert.deepEqual(typeKey(entry, "a"), entry);
    assert.deepEqual(typeKey(entry, "Enter"), entry);
  });
  test("pasted bare digits fill like typed ones", () => {
    assert.equal(isDigits("1234"), true);
    assert.equal(isDigits("12:34"), false);
    assert.equal(isDigits("1,5"), false);
    assert.equal(isDigits(""), false);
    assert.equal(entryText(entryFromDigits("1234"), ","), "0:12:34");
  });
  test("rawText is what was typed, for a switch to free text", () => {
    assert.equal(rawText(type("12,5")), "12,5");
    assert.equal(rawText(emptyEntry()), "");
  });
});
