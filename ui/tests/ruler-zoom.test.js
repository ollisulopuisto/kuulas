import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { rangeFromDrag, zoomToRange } from "../ruler-zoom.js";

const view = { scroll: 100, zoom: 2 };

describe("rangeFromDrag", () => {
  test("a drag maps pixels to whole frames in either order", () => {
    assert.deepEqual(rangeFromDrag(100, 200, view), { start: 150, end: 200 });
    assert.deepEqual(rangeFromDrag(200, 100, view), { start: 150, end: 200 });
  });

  test("a drag shorter than minPx is null", () => {
    assert.equal(rangeFromDrag(100, 107, { ...view, minPx: 8 }), null);
    assert.equal(rangeFromDrag(100, 100, view), null);
    assert.equal(rangeFromDrag(200, 195, view), null);
  });

  test("exactly minPx is not null", () => {
    assert.deepEqual(rangeFromDrag(100, 108, { ...view, minPx: 8 }), {
      start: 150,
      end: 154,
    });
  });

  test("a drag starting left of frame 0 clamps start to 0", () => {
    assert.deepEqual(rangeFromDrag(-300, -100, view), { start: 0, end: 50 });
  });

  test("pixels between frames round to whole frames", () => {
    assert.deepEqual(rangeFromDrag(101, 200, { scroll: 100, zoom: 3 }), {
      start: 134,
      end: 167,
    });
  });
});

describe("zoomToRange", () => {
  const base = { width: 1000, padding: 0.02, minZoom: 1, maxZoom: 20 };

  test("the range fills the width minus padding on each side", () => {
    assert.deepEqual(zoomToRange({ start: 100, end: 200 }, base), {
      scroll: 100 - 20 / 9.6,
      zoom: 9.6,
    });
  });

  test("padding defaults to 0.02 of the width", () => {
    assert.deepEqual(
      zoomToRange({ start: 100, end: 200 }, { width: 1000, minZoom: 1, maxZoom: 20 }),
      {
        scroll: 100 - 20 / 9.6,
        zoom: 9.6,
      },
    );
  });

  test("zoom is clamped into [minZoom, maxZoom]", () => {
    assert.deepEqual(zoomToRange({ start: 100, end: 200 }, { ...base, minZoom: 20, maxZoom: 40 }), {
      scroll: 100 - 20 / 20,
      zoom: 20,
    });
    assert.deepEqual(zoomToRange({ start: 100, end: 2000 }, { ...base, minZoom: 1, maxZoom: 20 }), {
      scroll: 80,
      zoom: 1,
    });
  });

  test("scroll never goes below 0", () => {
    assert.deepEqual(zoomToRange({ start: 1, end: 101 }, base), { scroll: 0, zoom: 9.6 });
  });

  test("clamped at maxZoom centres the range instead of padding from its start", () => {
    assert.deepEqual(
      zoomToRange({ start: 400, end: 500 }, { width: 1000, padding: 0.02, minZoom: 1, maxZoom: 2 }),
      { scroll: 200, zoom: 2 },
    );
  });

  test("a range wider than the view at minZoom uses minZoom", () => {
    assert.deepEqual(
      zoomToRange(
        { start: 500, end: 3500 },
        { width: 1000, padding: 0.02, minZoom: 0.5, maxZoom: 2 },
      ),
      { scroll: 460, zoom: 0.5 },
    );
  });
});
