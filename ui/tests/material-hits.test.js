import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { canShow, removedSummary, statusKey } from "../material-hits.js";

describe("material hits", () => {
  test("every reason has its own tag text key", () => {
    assert.equal(statusKey("cut"), "ui.find.removed.cut");
    assert.equal(statusKey("muted"), "ui.find.removed.muted");
    assert.equal(statusKey("gated"), "ui.find.removed.gated");
    assert.equal(statusKey("unused"), "ui.find.removed.unused");
  });
  test("an unknown reason reads as cut, never as nothing", () => {
    assert.equal(statusKey("???"), "ui.find.removed.cut");
  });
  test("only a hit that is on the timeline can be shown there", () => {
    assert.equal(canShow({ status: "muted", at: 0, track: "t" }), true);
    assert.equal(canShow({ status: "cut" }), false);
  });
  test("the summary names the count, and is absent without hits", () => {
    assert.deepEqual(removedSummary(4), { key: "ui.find.removed.summary", values: { count: 4 } });
    assert.equal(removedSummary(0), null);
  });
});
