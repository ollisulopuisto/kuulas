import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { fieldKey, fieldPaste, fieldText, fieldValue, openField } from "../time-entry.js";

// In plain text the browser types the key itself; the helper does the same.
function press(keys, start = openField("0:12:34,500")) {
  let field = start;
  for (const key of keys) {
    const result = fieldKey(field, key);
    field =
      !result.handled && field.free
        ? Object.assign({}, field, { text: field.text + key })
        : result.field;
  }
  return field;
}

describe("the field around the entry", () => {
  test("untouched, it shows the current time and jumps to exactly that text", () => {
    const field = openField("0:12:34,500");
    assert.equal(fieldText(field, ","), "0:12:34,500");
    assert.equal(fieldValue(field), "0:12:34,500");
  });
  test("the first digit starts a new entry, it does not append to the old time", () => {
    const field = press("110");
    assert.equal(fieldText(field, ","), "0:01:10");
    assert.equal(fieldValue(field), "70");
  });
  test("a fraction is passed on in plain seconds", () => {
    assert.equal(fieldValue(press("10,5")), "10.5");
    assert.equal(fieldValue(press("1,25")), "1.25");
  });
  test("Backspace or Delete on the untouched time clears it to zeros", () => {
    assert.equal(fieldText(fieldKey(openField("0:12:34"), "Backspace").field, ","), "0:00:00");
    assert.equal(fieldText(fieldKey(openField("0:12:34"), "Delete").field, ","), "0:00:00");
  });
  test("a sign turns the field to plain text, so +100 keeps meaning 100 seconds on", () => {
    const field = press("+100");
    assert.equal(field.free, true);
    assert.equal(fieldText(field, ","), "+100");
    assert.equal(fieldValue(field), "+100");
    assert.equal(fieldValue(press("-30")), "-30");
  });
  test("a colon or a unit after digits keeps what was typed", () => {
    assert.equal(fieldValue(press("1:")), "1:");
    assert.equal(fieldValue(press("500ms")), "500ms");
    assert.equal(fieldValue(press("12,5s")), "12,5s");
  });
  test("keys that are not part of a time are swallowed", () => {
    const result = fieldKey(press("12"), "x");
    assert.equal(result.handled, true);
    assert.equal(fieldText(result.field, ","), "0:00:12");
  });
  test("keys with a modifier or without a character are left alone", () => {
    assert.equal(fieldKey(press("1"), "ArrowLeft").handled, false);
    assert.equal(fieldKey(press("1"), "a", true).handled, false);
  });
  test("a pasted full timestamp becomes plain text; pasted digits fill like typing", () => {
    const stamp = fieldPaste(openField("0:00:01"), " 1:02:03,500 ");
    assert.equal(stamp.free, true);
    assert.equal(fieldValue(stamp), "1:02:03,500");
    const digits = fieldPaste(openField("0:00:01"), "1234");
    assert.equal(fieldText(digits, ","), "0:12:34");
  });
  test("plain text stays editable: the keys are no longer taken", () => {
    const free = press("+1");
    assert.equal(fieldKey(free, "5").handled, false);
  });
  test("in plain text the browser edits, so the text follows what it says", () => {
    const free = press("+1");
    assert.equal(fieldText({ ...free, text: "+15" }, ","), "+15");
  });
});
