import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { fuzzyFilter, fuzzyMatch } from "../fuzzy.js";

describe("fuzzy match", () => {
  test("an empty query matches everything", () => {
    assert.deepEqual(fuzzyMatch("", "Split").indices, []);
    assert.deepEqual(
      fuzzyFilter(["b", "a"], "").map((r) => r.item),
      ["b", "a"],
    );
  });

  test("letters must appear in order, case-insensitively", () => {
    assert.notEqual(fuzzyMatch("spl", "Split at playhead"), null);
    assert.notEqual(fuzzyMatch("SPH", "Split at playhead"), null);
    assert.equal(fuzzyMatch("lps", "Split"), null);
    assert.equal(fuzzyMatch("x", "Split"), null);
  });

  test("returns the indices to underline", () => {
    assert.deepEqual(fuzzyMatch("spt", "Split").indices, [0, 1, 4]);
  });

  test("a prefix beats a word start beats a scattered match", () => {
    const hits = fuzzyFilter(["Zoom to fit", "Mute track", "Split"], "s").map((r) => r.item);
    assert.equal(hits[0], "Split");
    const order = fuzzyFilter(["a-b-split", "split now", "xsplit"], "split").map((r) => r.item);
    assert.deepEqual(order, ["split now", "a-b-split", "xsplit"]);
  });

  test("ties keep the original order, and non-matches drop out", () => {
    const result = fuzzyFilter(["aa", "ab", "ac"], "a").map((r) => r.item);
    assert.deepEqual(result, ["aa", "ab", "ac"]);
    assert.deepEqual(fuzzyFilter(["aa"], "z"), []);
  });

  test("works on accented Finnish text", () => {
    assert.notEqual(fuzzyMatch("pät", "Pätkä"), null);
    assert.notEqual(fuzzyMatch("PÄT", "pätkä"), null);
  });

  test("a getter picks the text from objects", () => {
    const rows = fuzzyFilter([{ n: "Undo" }, { n: "Redo" }], "re", (x) => x.n);
    assert.deepEqual(
      rows.map((r) => r.item.n),
      ["Redo"],
    );
  });
});
