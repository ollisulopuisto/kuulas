import assert from "node:assert/strict";
import test from "node:test";
import { filterSteps, highlight } from "../history-filter.js";

test("filterSteps: empty or blank query returns same array object", () => {
  const steps = [
    { id: 1, label: "Leikkaa", when: 100 },
    { id: 2, label: "Liimaa", when: 200 },
  ];
  assert.equal(filterSteps(steps, ""), steps);
  assert.equal(filterSteps(steps, "   "), steps);
});

test("filterSteps: one word filter", () => {
  const steps = [
    { id: 1, label: "Poista leike", when: 100 },
    { id: 2, label: "Lisää raita", when: 200 },
    { id: 3, label: "Jaa leike", when: 300 },
  ];
  const res = filterSteps(steps, "leike");
  assert.deepEqual(res, [
    { id: 1, label: "Poista leike", when: 100 },
    { id: 3, label: "Jaa leike", when: 300 },
  ]);
});

test("filterSteps: two words (both needed)", () => {
  const steps = [
    { id: 1, label: "Poista puheen leike", when: 100 },
    { id: 2, label: "Poista musiikin raita", when: 200 },
    { id: 3, label: "Lisää puheen leike", when: 300 },
  ];
  const res = filterSteps(steps, "poista leike");
  assert.deepEqual(res, [{ id: 1, label: "Poista puheen leike", when: 100 }]);
});

test("filterSteps: case and ä/ö folding", () => {
  const steps = [
    { id: 1, label: "ÄÄNITYS käynnistyi", when: 100 },
    { id: 2, label: "äänitys päättyi", when: 200 },
    { id: 3, label: "Muu toimenpide", when: 300 },
  ];
  const res = filterSteps(steps, "äänitys");
  assert.equal(res.length, 2);
  assert.equal(res[0].id, 1);
  assert.equal(res[1].id, 2);

  const resUpper = filterSteps(steps, "ÄÄNITYS PÄÄTTYI");
  assert.equal(resUpper.length, 1);
  assert.equal(resUpper[0].id, 2);
});

test("filterSteps: order kept", () => {
  const steps = [
    { id: 5, label: "Kopioi", when: 50 },
    { id: 2, label: "Kopioi", when: 20 },
    { id: 8, label: "Kopioi", when: 80 },
  ];
  const res = filterSteps(steps, "kopioi");
  assert.deepEqual(
    res.map((s) => s.id),
    [5, 2, 8],
  );
});

test("highlight: blank query returns one segment with match: false", () => {
  assert.deepEqual(highlight("Poista leike", ""), [{ text: "Poista leike", match: false }]);
  assert.deepEqual(highlight("Poista leike", "   "), [{ text: "Poista leike", match: false }]);
});

test("highlight: single match", () => {
  assert.deepEqual(highlight("Poista leike", "leike"), [
    { text: "Poista ", match: false },
    { text: "leike", match: true },
  ]);
});

test("highlight: adjacent matches merged", () => {
  // query words "abc" and "def" in "abcdef"
  assert.deepEqual(highlight("abcdef", "abc def"), [{ text: "abcdef", match: true }]);
});

test("highlight: overlapping matches merged", () => {
  // "bcd" and "cde" in "abcdef"
  assert.deepEqual(highlight("abcdef", "bcd cde"), [
    { text: "a", match: false },
    { text: "bcde", match: true },
    { text: "f", match: false },
  ]);
});

test("highlight: no match returns one segment with match: false", () => {
  assert.deepEqual(highlight("Poista leike", "musiikki"), [{ text: "Poista leike", match: false }]);
});

test("highlight: case and ä/ö", () => {
  assert.deepEqual(highlight("ÄÄNI raita", "ääni"), [
    { text: "ÄÄNI", match: true },
    { text: " raita", match: false },
  ]);
});
