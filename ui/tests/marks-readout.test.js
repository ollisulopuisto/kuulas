import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { entryPatch, readoutRows } from "../marks-readout.js";

const RATE = 1000;
const fmt = (frame, rate) => `T${frame / rate}`;
const none = { inPoint: null, outPoint: null };

describe("readoutRows", () => {
  test("nothing set: three unset rows", () => {
    assert.deepEqual(readoutRows(none, RATE, fmt), {
      in: { set: false, text: null },
      out: { set: false, text: null },
      length: { set: false, text: null },
    });
  });
  test("a lone mark lights only itself", () => {
    const rows = readoutRows({ inPoint: 2000, outPoint: null }, RATE, fmt);
    assert.deepEqual(rows.in, { set: true, text: "T2" });
    assert.equal(rows.out.set, false);
    assert.equal(rows.length.set, false);
  });
  test("both marks give the length", () => {
    const rows = readoutRows({ inPoint: 2000, outPoint: 5500 }, RATE, fmt);
    assert.deepEqual(rows.length, { set: true, text: "T3.5" });
  });
  test("reversed or equal marks give no length", () => {
    assert.equal(readoutRows({ inPoint: 5, outPoint: 5 }, RATE, fmt).length.set, false);
    assert.equal(readoutRows({ inPoint: 9, outPoint: 5 }, RATE, fmt).length.set, false);
  });
  test("a mark at frame 0 is set", () => {
    assert.equal(readoutRows({ inPoint: 0, outPoint: null }, RATE, fmt).in.set, true);
  });
});

describe("entryPatch", () => {
  const state = { inPoint: 2000, outPoint: 5000 };
  test("typing the in mark sets it, in frames", () => {
    assert.deepEqual(entryPatch("in", "1:03,5", none, RATE), {
      ok: true,
      patch: { inPoint: 63500, outPoint: null },
    });
  });
  test("an in mark past the out mark drops the out mark (as the I key does)", () => {
    assert.deepEqual(entryPatch("in", "9", state, RATE), {
      ok: true,
      patch: { inPoint: 9000, outPoint: null },
    });
  });
  test("typing the out mark; before the in mark it replaces the in mark (as O does)", () => {
    assert.deepEqual(entryPatch("out", "7.25", state, RATE), {
      ok: true,
      patch: { inPoint: 2000, outPoint: 7250 },
    });
    assert.deepEqual(entryPatch("out", "1", state, RATE), {
      ok: true,
      patch: { inPoint: null, outPoint: 1000 },
    });
  });
  test("typing the length moves the out mark to in + length", () => {
    assert.deepEqual(entryPatch("length", "0:04,5", state, RATE), {
      ok: true,
      patch: { inPoint: 2000, outPoint: 6500 },
    });
  });
  test("a length needs an in mark and must be above zero", () => {
    assert.equal(entryPatch("length", "4", none, RATE).ok, false);
    assert.equal(entryPatch("length", "0", state, RATE).ok, false);
  });
  test("unreadable text is refused", () => {
    for (const which of ["in", "out", "length"]) {
      assert.deepEqual(entryPatch(which, "abc", state, RATE), { ok: false });
      assert.deepEqual(entryPatch(which, "", state, RATE), { ok: false });
      assert.deepEqual(entryPatch(which, "-3", state, RATE), { ok: false });
    }
  });
  test("a limit clamps to the end of the edit; a length that cannot fit is refused", () => {
    assert.deepEqual(entryPatch("out", "99", state, RATE, 8000), {
      ok: true,
      patch: { inPoint: 2000, outPoint: 8000 },
    });
    assert.deepEqual(entryPatch("length", "99", state, RATE, 8000), {
      ok: true,
      patch: { inPoint: 2000, outPoint: 8000 },
    });
    const atEnd = { inPoint: 8000, outPoint: null };
    assert.equal(entryPatch("length", "1", atEnd, RATE, 8000).ok, false);
  });
  test("the seconds are rounded to whole frames", () => {
    assert.equal(entryPatch("in", "0,0004", none, RATE).patch.inPoint, 0);
    assert.equal(entryPatch("in", "0,0006", none, RATE).patch.inPoint, 1);
  });
});
