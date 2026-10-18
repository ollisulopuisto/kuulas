import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  candidateBands,
  extractCurrent,
  flagFits,
  flagText,
  kindFacts,
  listedRows,
  previewBar,
  scrollToShow,
  sortedRows,
  stepTarget,
} from "../candidates-model.js";

const row = (id, start, extra = {}) => ({
  id,
  kind: "silence",
  state: "open",
  start,
  end: start === null ? null : start + 100,
  spans: start === null ? [] : [[start, start + 100]],
  tracks: ["a"],
  seconds: 2.4,
  ...extra,
});

describe("sortedRows and listedRows", () => {
  test("by time, candidates off the timeline last, ties by id", () => {
    const rows = [row("c", null), row("b", 500), row("a2", 100), row("a1", 100)];
    assert.deepEqual(
      sortedRows(rows).map((r) => r.id),
      ["a1", "a2", "b", "c"],
    );
  });

  test("Open only keeps the open ones", () => {
    const rows = [row("a", 1), row("b", 2, { state: "cut" }), row("c", 3, { state: "kept" })];
    assert.deepEqual(
      listedRows(rows, true).map((r) => r.id),
      ["a"],
    );
    assert.equal(listedRows(rows, false).length, 3);
  });

  test("does not change the list it is given", () => {
    const rows = [row("b", 5), row("a", 1)];
    sortedRows(rows);
    assert.equal(rows[0].id, "b");
  });
});

describe("kindFacts: every kind has a word and an icon, not only a colour", () => {
  test("the five kinds are distinct", () => {
    const kinds = ["silence", "filler", "retake", "breath", "marked"];
    const icons = kinds.map((k) => kindFacts(k).icon);
    assert.equal(new Set(icons).size, 5);
    assert.equal(kindFacts("filler").key, "ui.candidates.kind.filler");
  });
  test("an unknown kind reads as marked", () => {
    assert.equal(kindFacts("future-kind").key, "ui.candidates.kind.marked");
  });
});

describe("stepTarget", () => {
  const rows = [row("a", 100), row("b", 300), row("c", 600), row("gone", null)];
  test("next from the playhead: the first one that starts after it", () => {
    assert.equal(stepTarget(rows, { currentId: null, playhead: 0 }, 1).id, "a");
    assert.equal(stepTarget(rows, { currentId: null, playhead: 150 }, 1).id, "b");
  });
  test("previous from the playhead: the last one that starts before it", () => {
    assert.equal(stepTarget(rows, { currentId: null, playhead: 650 }, -1).id, "c");
    assert.equal(stepTarget(rows, { currentId: null, playhead: 300 }, -1).id, "a");
  });
  test("standing on the current one, the neighbour in the list", () => {
    assert.equal(stepTarget(rows, { currentId: "b", playhead: 300 }, 1).id, "c");
    assert.equal(stepTarget(rows, { currentId: "b", playhead: 300 }, -1).id, "a");
  });
  test("two candidates at one instant are both visited", () => {
    const twins = [row("a", 100), row("b", 100), row("c", 200)];
    assert.equal(stepTarget(twins, { currentId: "a", playhead: 100 }, 1).id, "b");
  });
  test("the playhead moved away from the current one: position wins", () => {
    assert.equal(stepTarget(rows, { currentId: "a", playhead: 700 }, -1).id, "c");
  });
  test("stops at the ends and skips candidates that are not on the timeline", () => {
    assert.equal(stepTarget(rows, { currentId: "c", playhead: 600 }, 1), null);
    assert.equal(stepTarget(rows, { currentId: "a", playhead: 100 }, -1), null);
    assert.equal(stepTarget([row("g", null)], { currentId: null, playhead: 0 }, 1), null);
  });
});

describe("extractCurrent", () => {
  const rows = [row("a", 1), row("b", 2)];
  test("the picked row, else null", () => {
    assert.equal(extractCurrent(rows, "b").id, "b");
    assert.equal(extractCurrent(rows, "zz"), null);
    assert.equal(extractCurrent(rows, null), null);
  });
});

describe("scrollToShow", () => {
  test("already in view: the scroll stays", () => {
    assert.equal(scrollToShow(5000, { scroll: 0, zoom: 10, width: 1000 }), 0);
  });
  test("off to the right: the start comes to a quarter of the width", () => {
    assert.equal(scrollToShow(40000, { scroll: 0, zoom: 10, width: 1000 }), 37500);
  });
  test("before the view, near the start: never negative", () => {
    assert.equal(scrollToShow(100, { scroll: 90000, zoom: 10, width: 1000 }), 0);
  });
  test("right at the edge counts as not visible", () => {
    assert.equal(scrollToShow(9990, { scroll: 0, zoom: 10, width: 1000 }), 7490);
  });
});

describe("candidateBands (the stripes across the lanes)", () => {
  const view = { scroll: 0, zoom: 10, width: 1000 };
  test("only open candidates, in pixels, with their lanes", () => {
    const rows = [
      row("a", 1000, { tracks: ["x", "y"] }),
      row("b", 3000, { state: "cut" }),
      row("c", 5000, { state: "kept" }),
    ];
    const bands = candidateBands(rows, { ...view, currentId: null });
    assert.equal(bands.length, 1);
    assert.deepEqual(
      { x0: bands[0].x0, x1: bands[0].x1, tracks: bands[0].tracks, current: bands[0].current },
      { x0: 100, x1: 110, tracks: ["x", "y"], current: false },
    );
  });
  test("a candidate outside the view is left out", () => {
    const bands = candidateBands([row("a", 20000), row("b", -5000)], { ...view, currentId: null });
    assert.equal(bands.length, 0);
  });
  test("a sliver is two pixels wide so it can still be seen", () => {
    const bands = candidateBands([row("a", 1000, { spans: [[1000, 1003]] })], {
      ...view,
      currentId: null,
    });
    assert.equal(bands[0].x1 - bands[0].x0, 2);
  });
  test("the current one is marked and drawn last (on top)", () => {
    const bands = candidateBands([row("a", 1000), row("b", 2000)], { ...view, currentId: "a" });
    assert.deepEqual(
      bands.map((b) => [b.id, b.current]),
      [
        ["b", false],
        ["a", true],
      ],
    );
  });
  test("a candidate in two pieces has two bands but one flag, on the first", () => {
    const bands = candidateBands(
      [
        row("a", 1000, {
          spans: [
            [1000, 1100],
            [3000, 3100],
          ],
        }),
      ],
      {
        ...view,
        currentId: null,
      },
    );
    assert.deepEqual(
      bands.map((b) => b.flag),
      [true, false],
    );
  });
  test("a cut or kept current one is not drawn", () => {
    const bands = candidateBands([row("a", 1000, { state: "cut" })], { ...view, currentId: "a" });
    assert.equal(bands.length, 0);
  });
});

describe("the ruler flag", () => {
  const t = (key, values) => `${key}|${values.seconds}`;
  test("flagText carries the length with one decimal", () => {
    assert.equal(
      flagText({ seconds: 2.4 }, t, (n) => n.toFixed(1)),
      "ui.candidates.flag|2.4",
    );
    assert.equal(
      flagText({ seconds: 3 }, t, (n) => n.toFixed(1)),
      "ui.candidates.flag|3.0",
    );
  });
  test("the text shows only when it fits in the band with room to spare", () => {
    assert.equal(flagFits(80, 60), true);
    assert.equal(flagFits(70, 60), false);
    assert.equal(flagFits(10, 60), false);
  });
});

describe("previewBar", () => {
  test("before, skipped and after, in seconds", () => {
    const preview = { from: 0, to: 1000, skip: [[200, 500]] };
    assert.deepEqual(previewBar(preview, 100), { before: 2, skipped: 3, after: 5 });
  });
  test("several skipped pieces add up", () => {
    const preview = {
      from: 100,
      to: 900,
      skip: [
        [200, 300],
        [400, 450],
      ],
    };
    assert.deepEqual(previewBar(preview, 100), { before: 1, skipped: 1.5, after: 4.5 });
  });
  test("nothing to preview: null", () => {
    assert.equal(previewBar(null, 100), null);
    assert.equal(previewBar({ from: 0, to: 10, skip: [] }, 100), null);
  });
});
