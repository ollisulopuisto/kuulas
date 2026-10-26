import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { implicitMarkPlan, lengthPill, markDrawing, setInPoint, setOutPoint } from "../marks.js";

describe("setting the in and out marks", () => {
  test("a lone mark is set as it is", () => {
    assert.deepEqual(setOutPoint({ inPoint: null, outPoint: null }, 500), {
      inPoint: null,
      outPoint: 500,
    });
    assert.deepEqual(setInPoint({ inPoint: null, outPoint: null }, 500), {
      inPoint: 500,
      outPoint: null,
    });
  });
  test("an out mark before the in mark replaces the in mark", () => {
    assert.deepEqual(setOutPoint({ inPoint: 800, outPoint: null }, 300), {
      inPoint: null,
      outPoint: 300,
    });
  });
  test("an in mark after the out mark replaces the out mark", () => {
    assert.deepEqual(setInPoint({ inPoint: null, outPoint: 300 }, 800), {
      inPoint: 800,
      outPoint: null,
    });
  });
  test("a mark that keeps the order leaves the other one alone", () => {
    assert.deepEqual(setOutPoint({ inPoint: 100, outPoint: null }, 300), {
      inPoint: 100,
      outPoint: 300,
    });
    assert.deepEqual(setInPoint({ inPoint: null, outPoint: 300 }, 100), {
      inPoint: 100,
      outPoint: 300,
    });
  });
  test("moving a mark onto the other makes no range, so the other goes", () => {
    assert.deepEqual(setOutPoint({ inPoint: 300, outPoint: null }, 300), {
      inPoint: null,
      outPoint: 300,
    });
  });
});

describe("what to draw for the marks", () => {
  test("nothing for no marks", () => {
    assert.deepEqual(markDrawing({ inPoint: null, outPoint: null }), {
      inFrame: null,
      outFrame: null,
      range: null,
      guessed: { in: false, out: false },
    });
  });
  test("a lone out mark is drawn, with no range tint", () => {
    assert.deepEqual(markDrawing({ inPoint: null, outPoint: 500 }), {
      inFrame: null,
      outFrame: 500,
      range: null,
      guessed: { in: false, out: false },
    });
  });
  test("both marks give the range tint", () => {
    assert.deepEqual(markDrawing({ inPoint: 100, outPoint: 500 }), {
      inFrame: 100,
      outFrame: 500,
      range: { start: 100, end: 500 },
      guessed: { in: false, out: false },
    });
  });
  test("reversed marks (an old saved state) draw no range tint", () => {
    assert.equal(markDrawing({ inPoint: 500, outPoint: 100 }).range, null);
  });
});

describe("lengthPill (the length on the ruler band)", () => {
  const range = { start: 1000, end: 3000 };
  const view = { scroll: 0, zoom: 10, width: 800, textWidth: 50 };
  test("centred on the band, as wide as the label plus its padding", () => {
    // band 100..300 px, pill 62 wide
    assert.deepEqual(lengthPill({ range, ...view }), { x: 169, width: 62, center: 200 });
  });
  test("no pill without a range", () => {
    assert.equal(lengthPill({ range: null, ...view }), null);
  });
  test("hidden when the band is narrower than the pill plus 16 px", () => {
    // pill 62 + 16 = 78 px needed; 780 frames at 10 frames/px = 78 px fits, 770 does not
    assert.notEqual(lengthPill({ range: { start: 0, end: 780 }, ...view }), null);
    assert.equal(lengthPill({ range: { start: 0, end: 770 }, ...view }), null);
  });
  test("only the visible part of the band counts and carries the pill", () => {
    const wide = { start: -5000, end: 5000 };
    const pill = lengthPill({ range: wide, ...view });
    assert.equal(pill.center, 250); // visible x 0..500
    const edge = lengthPill({ range: { start: 7000, end: 12000 }, ...view });
    assert.equal(edge.center, 750); // 100 visible px at x 700..800
    assert.equal(lengthPill({ range: { start: 7300, end: 12000 }, ...view }), null); // 50 px left
  });
});

describe("a click completes the lone mark", () => {
  // Owner, 2026-10-25: with only I set, a click after it is the O; with only O set, a click
  // before it is the I. A click on the wrong side changes nothing.
  const lone = (inPoint, outPoint) => ({ inPoint, outPoint, ghost: null, guessedMarks: {} });

  test("after I, a click later on sets O", () => {
    const patch = implicitMarkPlan(lone(100, null), 300);
    assert.equal(patch.inPoint, 100);
    assert.equal(patch.outPoint, 300);
  });

  test("after O, a click earlier sets I", () => {
    const patch = implicitMarkPlan(lone(null, 500), 200);
    assert.equal(patch.inPoint, 200);
    assert.equal(patch.outPoint, 500);
  });

  test("a click on the wrong side of the lone mark does nothing", () => {
    assert.equal(implicitMarkPlan(lone(100, null), 50), null);
    assert.equal(implicitMarkPlan(lone(null, 500), 600), null);
  });

  test("with both marks set, or none, a click does nothing", () => {
    assert.equal(implicitMarkPlan(lone(100, 500), 300), null);
    assert.equal(implicitMarkPlan(lone(null, null), 300), null);
  });
});
