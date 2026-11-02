import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  adjacentMarker,
  chapterCount,
  draggedMarkerStart,
  flagLayout,
  markerAt,
  markerIdAtX,
  markerRows,
  nextMarkerName,
  regionCount,
  regionFromRange,
} from "../markers-model.js";

const m = (id, start, extra = {}) => ({ id, name: id, start, kind: "marker", ...extra });

describe("markerRows", () => {
  test("by start, ties by id, with seconds and a length for regions", () => {
    const rows = markerRows(
      [
        m("b", 96_000),
        m("a2", 48_000),
        m("a1", 48_000),
        m("r", 0, { kind: "region", end: 24_000 }),
      ],
      48_000,
    );
    assert.deepEqual(
      rows.map((r) => r.id),
      ["r", "a1", "a2", "b"],
    );
    assert.equal(rows[0].seconds, 0);
    assert.equal(rows[0].length, 0.5);
    assert.equal(rows[1].length, null);
  });

  test("none is an empty list", () => {
    assert.deepEqual(markerRows(undefined, 48_000), []);
  });
});

describe("adjacentMarker", () => {
  const list = [m("a", 100), m("b", 200), m("c", 300, { kind: "region", end: 400 })];
  test("next is strictly after the frame, previous strictly before", () => {
    assert.equal(adjacentMarker(list, 100, 1).id, "b");
    assert.equal(adjacentMarker(list, 150, 1).id, "b");
    assert.equal(adjacentMarker(list, 200, -1).id, "a");
    assert.equal(adjacentMarker(list, 250, -1).id, "b");
  });
  test("a region counts at its start; no more markers is null, no wrapping", () => {
    assert.equal(adjacentMarker(list, 250, 1).id, "c");
    assert.equal(adjacentMarker(list, 300, 1), null);
    assert.equal(adjacentMarker(list, 100, -1), null);
    assert.equal(adjacentMarker([], 0, 1), null);
  });
  test("unsorted input is fine", () => {
    assert.equal(adjacentMarker([m("z", 900), m("y", 500)], 0, 1).id, "y");
  });
});

describe("markerAt", () => {
  test("the marker starting at the frame, if any", () => {
    assert.equal(markerAt([m("a", 100), m("b", 200)], 200).id, "b");
    assert.equal(markerAt([m("a", 100)], 101), null);
  });
});

describe("regionFromRange", () => {
  test("in before out", () => assert.deepEqual(regionFromRange(10, 50), { start: 10, end: 50 }));
  test("out before in is swapped", () =>
    assert.deepEqual(regionFromRange(50, 10), { start: 10, end: 50 }));
  test("a missing point or an empty range is null", () => {
    assert.equal(regionFromRange(null, 50), null);
    assert.equal(regionFromRange(10, null), null);
    assert.equal(regionFromRange(10, 10), null);
  });
});

describe("nextMarkerName", () => {
  test("the lowest number not taken", () => {
    const list = [m("a", 1, { name: "Marker 1" }), m("b", 2, { name: "Marker 2" })];
    assert.equal(nextMarkerName(list, "Marker"), "Marker 3");
    assert.equal(nextMarkerName([], "Marker"), "Marker 1");
    assert.equal(nextMarkerName([m("a", 1, { name: "Marker 2" })], "Marker"), "Marker 1");
  });
});

describe("counts", () => {
  test("chapters and regions", () => {
    const list = [m("a", 1, { kind: "chapter" }), m("b", 2), m("r", 3, { kind: "region", end: 9 })];
    assert.equal(chapterCount(list), 1);
    assert.equal(regionCount(list), 1);
    assert.equal(chapterCount(undefined), 0);
  });
});

describe("flagLayout", () => {
  const measure = (text) => text.length * 6;
  const view = { scroll: 0, zoom: 100, width: 400, measure };
  const layout = (list, extra = {}) => flagLayout(list, { ...view, ...extra });

  test("a point flag sits at its x with its name beside it", () => {
    const [flag] = layout([m("Intro", 5000)]).flags;
    assert.equal(flag.x, 50);
    assert.equal(flag.label, "Intro");
    assert.ok(flag.labelX > flag.x);
  });

  test("a name that would run into the next flag is dropped, never overlapped", () => {
    const { flags } = layout([m("A long name", 1000), m("Next", 2000)]);
    assert.equal(flags[0].label, null);
    assert.equal(flags[1].label, "Next");
  });

  test("labels never overlap whatever the spacing", () => {
    const list = Array.from({ length: 30 }, (_, i) => m(`Mark ${i}`, i * 700));
    const { flags } = layout(list);
    const shown = flags.filter((f) => f.label);
    for (let i = 1; i < shown.length; i += 1) {
      const before = shown[i - 1];
      assert.ok(before.labelX + measure(before.label) <= shown[i].x, "label runs into the flag");
    }
  });

  test("flags outside the view are left out; a region reaching in is clipped to it", () => {
    const { flags, bars } = layout(
      [
        m("gone", -50_000),
        m("far", 90_000),
        m("in", 10_000),
        m("r", -2000, { kind: "region", end: 3000 }),
      ],
      { scroll: 0 },
    );
    assert.deepEqual(
      flags.map((f) => f.id),
      ["in"],
    );
    assert.equal(bars.length, 1);
    assert.equal(bars[0].x0, 0);
    assert.equal(bars[0].x1, 30);
    assert.equal(bars[0].startsInView, false);
  });

  test("a region carries its name when the bar is wide enough", () => {
    const [wide] = layout([m("Interview", 0, { kind: "region", end: 20_000 })]).bars;
    assert.equal(wide.label, "Interview");
    const [narrow] = layout([m("Interview", 0, { kind: "region", end: 1000 })]).bars;
    assert.equal(narrow.label, null);
  });

  test("scroll and zoom move the flags", () => {
    const [flag] = layout([m("a", 6000)], { scroll: 2000, zoom: 50 }).flags;
    assert.equal(flag.x, 80);
  });

  test("a flag keeps its kind for the shape it is drawn in", () => {
    const { flags } = layout([m("a", 100, { kind: "chapter" }), m("b", 20_000)]);
    assert.deepEqual(
      flags.map((f) => f.kind),
      ["chapter", "marker"],
    );
  });
});

describe("which marker a ruler pointer is on", () => {
  const view = { scroll: 0, zoom: 10, width: 1000 };
  const markers = [
    { id: "a", kind: "marker", name: "A", start: 1000 },
    { id: "r", kind: "region", name: "R", start: 3000, end: 5000 },
  ];
  test("a flag: from its pole across its notch", () => {
    assert.equal(markerIdAtX(markers, view, 100), "a");
    assert.equal(markerIdAtX(markers, view, 106), "a");
    assert.equal(markerIdAtX(markers, view, 140), null);
  });
  test("a region: anywhere along its bar", () => {
    assert.equal(markerIdAtX(markers, view, 400), "r");
    assert.equal(markerIdAtX(markers, view, 600), null);
  });
});

test("draggedMarkerStart: pointer frame minus the grab offset, clamped at zero", () => {
  assert.equal(draggedMarkerStart(100, 500), 400);
  assert.equal(draggedMarkerStart(0, 48000), 48000);
  // A grab near the flag's left edge dragged to the ruler's start never goes negative.
  assert.equal(draggedMarkerStart(240, 100), 0);
  // Sub-frame pointers round to the nearest frame.
  assert.equal(draggedMarkerStart(0, 100.6), 101);
});
