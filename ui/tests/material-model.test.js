import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { barShares, FILTERS, filterRows, lengthText, stateKey } from "../material-model.js";

const row = (id, state, extra = {}) => ({
  id,
  name: `file ${id}`,
  state,
  seconds: 100,
  used_s: 0,
  cut_s: 0,
  unused_s: 100,
  missing: false,
  recorded: false,
  ...extra,
});

const rows = [
  row("a", "used", { used_s: 100, unused_s: 0 }),
  row("b", "partly", { used_s: 40, unused_s: 60, recorded: true }),
  row("c", "unused", { recorded: true }),
  row("d", "cut", { cut_s: 100, unused_s: 0 }),
];

describe("filterRows", () => {
  test("the filters, in the order the panel shows them", () => {
    assert.deepEqual(FILTERS, ["all", "timeline", "unused", "takes"]);
  });

  test("all, on the timeline (played or cut), not on the timeline, takes", () => {
    const ids = (filter) => filterRows(rows, filter, "").map((r) => r.id);
    assert.deepEqual(ids("all"), ["a", "b", "c", "d"]);
    assert.deepEqual(ids("timeline"), ["a", "b", "d"]);
    assert.deepEqual(ids("unused"), ["c"]);
    assert.deepEqual(ids("takes"), ["b", "c"]);
  });

  test("a text filter on the name, any case, together with the filter", () => {
    assert.deepEqual(
      filterRows(rows, "all", "FILE b").map((r) => r.id),
      ["b"],
    );
    assert.deepEqual(filterRows(rows, "unused", "file b"), []);
  });
});

describe("barShares", () => {
  test("the played, cut and unused shares of the recording, summing to 1", () => {
    const shares = barShares(row("b", "partly", { used_s: 40, cut_s: 10, unused_s: 50 }));
    assert.deepEqual(shares, { used: 0.4, cut: 0.1, unused: 0.5 });
  });

  test("a zero-length recording is all unused, never NaN", () => {
    assert.deepEqual(barShares(row("z", "unused", { seconds: 0, unused_s: 0 })), {
      used: 0,
      cut: 0,
      unused: 1,
    });
  });
});

describe("lengthText and stateKey", () => {
  test("m:ss under an hour, h:mm:ss above", () => {
    assert.equal(lengthText(65), "1:05");
    assert.equal(lengthText(3725), "1:02:05");
    assert.equal(lengthText(0), "0:00");
  });

  test("the message key of a row's state", () => {
    assert.equal(stateKey(row("a", "used")), "ui.material.state.used");
    assert.equal(stateKey(row("a", "used", { missing: true })), "ui.material.state.missing");
  });
});
