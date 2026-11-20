import assert from "node:assert/strict";
import { test } from "node:test";
import { revealHelpTarget } from "../help-reveal.js";

test("Show me opens enclosing disclosures before scrolling to a hidden control", () => {
  const outer = { tagName: "DETAILS", open: false, parentElement: null };
  const inner = { tagName: "DETAILS", open: false, parentElement: outer };
  const target = { tagName: "BUTTON", parentElement: inner, closest: () => null };
  revealHelpTarget(target);
  assert.equal(outer.open, true);
  assert.equal(inner.open, true);
});
test("a sidebar target requests the real panel rather than just unhiding its DOM", () => {
  const calls = [];
  const target = { parentElement: null, closest: () => ({ dataset: { panel: "inspector" } }) };
  revealHelpTarget(target, (name) => calls.push(name));
  assert.deepEqual(calls, ["inspector"]);
});
test("Show me does not invent a panel for global controls", () => {
  revealHelpTarget({ closest: () => null, parentElement: null }, () => assert.fail("no panel"));
});
