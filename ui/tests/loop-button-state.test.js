// The loop toggle must show clearly when it is on: an accent fill and border, not
// just the faint pressed surface every toggle gets.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const css = readFileSync(new URL("../style.css", import.meta.url), "utf8");

function ruleBody(selector) {
  const start = css.indexOf(`${selector} {`);
  assert.notEqual(start, -1, `${selector} has a rule`);
  return css.slice(start, css.indexOf("}", start));
}

test("the pressed loop button is filled and outlined with the accent", () => {
  const body = ruleBody('.t-row .button.ghost[aria-pressed="true"]');
  assert.match(body, /background:\s*var\(--accent-subtle\)/);
  assert.match(body, /border-color:\s*var\(--accent\)/);
  assert.match(body, /color:\s*var\(--accent-text\)/);
});
