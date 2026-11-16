import assert from "node:assert/strict";
import { test } from "node:test";
import { restoreCorrectionFocus, shouldFocusPutBack } from "../transcript-focus.js";

test("finishing a correction returns focus to the transcript only when the field still has focus", () => {
  const input = {};
  const timeline = {};
  const doc = { activeElement: input };
  let focused = 0;
  const root = { ownerDocument: doc, focus: () => focused++ };
  restoreCorrectionFocus(root, input);
  assert.equal(focused, 1);
  doc.activeElement = timeline;
  restoreCorrectionFocus(root, input);
  assert.equal(focused, 1);
});

test("a delayed restore preview never pulls focus away from the user's new target", () => {
  const button = {};
  const timeline = {};
  const doc = { activeElement: button };
  const root = { ownerDocument: doc, contains: (element) => element === button };
  assert.equal(shouldFocusPutBack(root, button), true);
  doc.activeElement = timeline;
  assert.equal(shouldFocusPutBack(root, button), false);
});
