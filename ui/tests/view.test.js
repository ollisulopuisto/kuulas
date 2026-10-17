import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  backView,
  clampScroll,
  createViewHistory,
  describeZoom,
  fitRange,
  fitTarget,
  forwardView,
  initialViews,
  overviewScroll,
  overviewWindow,
  pickAnchor,
  rememberView,
  SNAP_TOLERANCE,
  snapZoom,
  spanParts,
  stepZoom,
  toggleView,
  visitView,
  zoomAt,
  zoomLevels,
} from "../view.js";

const RATE = 48_000;
const WIDTH = 1000;
const TEN_MIN = 600 * RATE;
const levels = zoomLevels({ width: WIDTH, rate: RATE, totalFrames: TEN_MIN });
const at = (seconds) => levels.find((l) => l.seconds === seconds);

describe("zoom snap levels", () => {
  test("run from the whole edit down to samples, named by time on screen", () => {
    assert.equal(levels[0].kind, "whole");
    assert.equal(levels[0].zoom, TEN_MIN / WIDTH);
    assert.equal(levels.at(-1).kind, "samples");
    const seconds = levels.filter((l) => l.kind === "time").map((l) => l.seconds);
    // The 10 min level is the whole edit here, so it is not listed twice.
    assert.deepEqual(seconds, [300, 120, 60, 30, 10, 5, 2, 1, 0.5, 0.1]);
    for (const l of levels.filter((x) => x.kind === "time")) {
      assert.ok(Math.abs(l.zoom - (l.seconds * RATE) / WIDTH) < 1e-9);
    }
  });

  test("zoom strictly decreases down the list", () => {
    for (let i = 1; i < levels.length; i += 1) assert.ok(levels[i].zoom < levels[i - 1].zoom);
  });

  test("a short edit drops the levels wider than itself", () => {
    const short = zoomLevels({ width: WIDTH, rate: RATE, totalFrames: 45 * RATE });
    assert.equal(short[0].kind, "whole");
    assert.deepEqual(
      short.filter((l) => l.kind === "time").map((l) => l.seconds),
      [30, 10, 5, 2, 1, 0.5, 0.1],
    );
  });

  test("an empty edit still has a usable whole level", () => {
    const empty = zoomLevels({ width: WIDTH, rate: RATE, totalFrames: 0 });
    assert.equal(empty[0].kind, "whole");
    assert.ok(empty[0].zoom > 0);
  });

  test("a release within 8 % settles on a level, further away does not", () => {
    const two = at(2).zoom;
    assert.equal(snapZoom(two * (1 + SNAP_TOLERANCE * 0.9), levels), two);
    assert.equal(snapZoom(two / (1 + SNAP_TOLERANCE * 0.9), levels), two);
    const off = two * 1.2;
    assert.equal(snapZoom(off, levels), off);
  });

  test("= and - step through the levels, from a level or from between two", () => {
    assert.equal(stepZoom(at(2).zoom, levels, +1), at(1).zoom);
    assert.equal(stepZoom(at(2).zoom, levels, -1), at(5).zoom);
    const between = (at(2).zoom + at(1).zoom) / 2;
    assert.equal(stepZoom(between, levels, +1), at(1).zoom);
    assert.equal(stepZoom(between, levels, -1), at(2).zoom);
  });

  test("stepping stops at both ends", () => {
    const closest = levels.at(-1).zoom;
    assert.equal(stepZoom(closest, levels, +1), closest);
    assert.equal(stepZoom(levels[0].zoom, levels, -1), levels[0].zoom);
  });

  test("describeZoom names a level, a samples view and a free zoom", () => {
    assert.deepEqual(describeZoom(at(2).zoom, levels, { width: WIDTH, rate: RATE }), {
      kind: "time",
      seconds: 2,
    });
    assert.equal(describeZoom(levels[0].zoom, levels, { width: WIDTH, rate: RATE }).kind, "whole");
    assert.equal(
      describeZoom(levels.at(-1).zoom, levels, { width: WIDTH, rate: RATE }).kind,
      "samples",
    );
    const free = describeZoom(at(2).zoom * 1.5, levels, { width: WIDTH, rate: RATE });
    assert.equal(free.kind, "time");
    assert.ok(Math.abs(free.seconds - 3) < 1e-9);
  });

  test("spanParts picks minutes, seconds or milliseconds", () => {
    assert.deepEqual(spanParts(1800), { unit: "min", value: 30 });
    assert.deepEqual(spanParts(90), { unit: "min", value: 1.5 });
    assert.deepEqual(spanParts(60), { unit: "min", value: 1 });
    assert.deepEqual(spanParts(30), { unit: "s", value: 30 });
    assert.deepEqual(spanParts(2), { unit: "s", value: 2 });
    assert.deepEqual(spanParts(0.5), { unit: "ms", value: 500 });
    assert.deepEqual(spanParts(0.1), { unit: "ms", value: 100 });
    assert.deepEqual(spanParts(3.456), { unit: "s", value: 3.5 });
  });
});

describe("zoom anchor", () => {
  test("zoomAt keeps the anchor frame at the same x", () => {
    const next = zoomAt({ zoom: 100, scroll: 10_000 }, 30_000, 25);
    assert.equal((30_000 - next.scroll) / next.zoom, (30_000 - 10_000) / 100);
  });

  test("zoomAt never scrolls before the start", () => {
    const next = zoomAt({ zoom: 10, scroll: 0 }, 50, 1000);
    assert.equal(next.scroll, 0);
  });

  test("clampScroll allows half a screen of room after the end", () => {
    assert.equal(clampScroll(-5, 10, 1000, 1_000_000), 0);
    assert.equal(clampScroll(5_000_000, 10, 1000, 1_000_000), 1_000_000 - 5000);
    assert.equal(clampScroll(7, 1000, 1000, 1_000_000), 0, "everything fits: no scroll");
  });

  test("order: the last edit point, else the pointer, else the playhead", () => {
    assert.deepEqual(pickAnchor({ lastEdit: 500, pointerFrame: 900, playhead: 1 }), {
      frame: 500,
      source: "edit",
    });
    assert.deepEqual(pickAnchor({ lastEdit: null, pointerFrame: 900, playhead: 1 }), {
      frame: 900,
      source: "pointer",
    });
    assert.deepEqual(pickAnchor({ lastEdit: null, pointerFrame: null, playhead: 1 }), {
      frame: 1,
      source: "playhead",
    });
    assert.equal(pickAnchor({ lastEdit: 0, pointerFrame: 9, playhead: 1 }).source, "edit");
  });
});

describe("Z toggles a close view and a wide view", () => {
  const ctx = (anchorFrame) => ({ anchorFrame, width: WIDTH, levels, totalFrames: TEN_MIN });

  test("starts wide; the first Z goes to the 2 s close view around the anchor", () => {
    const views = initialViews();
    assert.equal(views.current, "wide");
    const wide = { zoom: levels[0].zoom, scroll: 0 };
    const anchor = 100 * RATE;
    const next = toggleView(views, wide, ctx(anchor));
    assert.equal(next.views.current, "close");
    assert.equal(next.zoom, at(2).zoom);
    // The anchor was at x=100*48000/(600*48000/1000)=166.7; it stays there.
    const before = (anchor - wide.scroll) / wide.zoom;
    assert.ok(Math.abs((anchor - next.scroll) / next.zoom - before) < 1);
  });

  test("Z again returns to the wide view exactly as it was left", () => {
    const wide = { zoom: at(30).zoom, scroll: 123_456 };
    const toClose = toggleView(rememberView(initialViews(), wide), wide, ctx(200 * RATE));
    const back = toggleView(toClose.views, { zoom: toClose.zoom, scroll: toClose.scroll }, ctx(0));
    assert.equal(back.views.current, "wide");
    assert.equal(back.zoom, wide.zoom);
    assert.equal(back.scroll, wide.scroll);
  });

  test("the close view remembers its level, not its position", () => {
    const wide = { zoom: levels[0].zoom, scroll: 0 };
    const first = toggleView(initialViews(), wide, ctx(10 * RATE));
    const adjusted = rememberView(first.views, { zoom: at(0.5).zoom, scroll: first.scroll });
    const back = toggleView(adjusted, { zoom: at(0.5).zoom, scroll: first.scroll }, ctx(0));
    const again = toggleView(back.views, { zoom: back.zoom, scroll: back.scroll }, ctx(400 * RATE));
    assert.equal(again.zoom, at(0.5).zoom);
    const x = (400 * RATE - again.scroll) / again.zoom;
    assert.ok(x >= 0 && x <= WIDTH, "the new anchor is on screen");
  });

  test("an anchor that is off screen is centred", () => {
    const wide = { zoom: at(10).zoom, scroll: 0 };
    const next = toggleView(initialViews(), wide, ctx(300 * RATE));
    const x = (300 * RATE - next.scroll) / next.zoom;
    assert.ok(Math.abs(x - WIDTH / 2) < 1);
  });

  test("= and - adjust whichever view is current", () => {
    let views = toggleView(initialViews(), { zoom: levels[0].zoom, scroll: 0 }, ctx(0)).views;
    views = rememberView(views, { zoom: at(1).zoom, scroll: 0 });
    assert.equal(views.close.zoom, at(1).zoom);
    assert.equal(views.wide.zoom, levels[0].zoom);
  });
});

describe("view history (never undo history)", () => {
  const v = (n) => ({ zoom: n, scroll: 0 });

  test("Alt+Z steps back, Shift+Alt+Z forward", () => {
    let h = createViewHistory();
    for (const n of [1, 2, 3]) h = visitView(h, v(n));
    const back = backView(h);
    assert.deepEqual(back.view, v(2));
    const back2 = backView(back.history);
    assert.deepEqual(back2.view, v(1));
    assert.equal(backView(back2.history).view, null, "nothing before the first");
    assert.deepEqual(forwardView(back2.history).view, v(2));
  });

  test("a new visit after stepping back drops the forward views", () => {
    let h = createViewHistory();
    for (const n of [1, 2, 3]) h = visitView(h, v(n));
    h = backView(h).history;
    h = visitView(h, v(9));
    assert.equal(forwardView(h).view, null);
    assert.deepEqual(backView(h).view, v(2));
  });

  test("the same view twice is one entry, and the list is capped", () => {
    let h = createViewHistory(3);
    h = visitView(h, v(1));
    h = visitView(h, v(1));
    assert.equal(h.entries.length, 1);
    for (const n of [2, 3, 4, 5]) h = visitView(h, v(n));
    assert.equal(h.entries.length, 3);
    assert.deepEqual(h.entries.at(-1), v(5));
  });
});

describe("fitting", () => {
  test("fitRange puts the range in view with a margin", () => {
    const { zoom, scroll } = fitRange({ start: 10_000, end: 110_000, width: 1000, padding: 0.05 });
    assert.ok(scroll < 10_000);
    assert.ok(scroll + 1000 * zoom > 110_000);
    assert.ok(Math.abs(10_000 - scroll - 50 * zoom) < 1);
  });

  test("fitTarget: the selection, else in to out, else the whole edit", () => {
    const project = {
      tracks: [
        { id: "t1", clips: [{ id: "a", start: 100, length: 50 }] },
        { id: "t2", clips: [{ id: "b", start: 400, length: 100 }] },
      ],
    };
    const base = { project, selection: new Set(), inPoint: null, outPoint: null };
    assert.deepEqual(fitTarget({ ...base, selection: new Set(["a", "b"]) }), {
      start: 100,
      end: 500,
    });
    assert.deepEqual(fitTarget({ ...base, inPoint: 200, outPoint: 300 }), {
      start: 200,
      end: 300,
    });
    assert.deepEqual(fitTarget(base), { start: 0, end: 500 });
    assert.deepEqual(fitTarget({ ...base, selection: new Set(["gone"]) }), { start: 0, end: 500 });
  });
});

describe("overview strip", () => {
  test("the box shows the visible part of the whole edit", () => {
    const box = overviewWindow({ total: 1000, scroll: 250, zoom: 1, width: 500, strip: 200 });
    assert.deepEqual(box, { x: 50, w: 100 });
  });

  test("a click centres the visible part, clamped to the edit", () => {
    const params = { total: 1000, zoom: 1, width: 500, strip: 200 };
    assert.equal(overviewScroll({ ...params, x: 100 }), 250);
    assert.equal(overviewScroll({ ...params, x: 0 }), 0);
    assert.equal(overviewScroll({ ...params, x: 200 }), 1000 - 250);
  });

  test("the box never leaves the strip", () => {
    const box = overviewWindow({ total: 1000, scroll: 900, zoom: 10, width: 500, strip: 200 });
    assert.ok(box.x + box.w <= 200 + 1e-9);
  });
});
