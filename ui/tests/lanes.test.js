import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  BUS_HEIGHT,
  clampLaneHeight,
  clipEnd,
  DEFAULT_LANE,
  dbToY,
  hitTest,
  layoutRows,
  projectEnd,
  RULER_HEIGHT,
  rowAt,
  visibleRows,
  yToDb,
} from "../lanes.js";

const project = {
  rate: 48_000,
  buses: [{ id: "b1", name: "Voices" }],
  tracks: [
    {
      id: "t1",
      clips: [
        { id: "c1", start: 1000, offset: 500, length: 1000, gain_db: 0, envelope: [[1000, 6]] },
        { id: "c2", start: 2000, offset: 0, length: 1000, gain_db: 0, envelope: [] },
      ],
    },
    { id: "t2", clips: [] },
  ],
};
const view = { scroll: 0, zoom: 10, scrollY: 0, width: 800, height: 400 };

describe("lane layout", () => {
  test("tracks on no bus first; a bus with no tracks goes last; no gaps", () => {
    const layout = layoutRows(project, 48);
    assert.deepEqual(
      layout.rows.map((r) => [r.kind, r.id, r.top, r.height]),
      [
        ["track", "t1", 0, 48],
        ["track", "t2", 48, 48],
        ["bus", "b1", 96, BUS_HEIGHT],
      ],
    );
    assert.equal(layout.height, 96 + BUS_HEIGHT);
  });

  test("a bus sits above its tracks, which gather under it; others keep their place", () => {
    // Owner, 2026-10-17: a bus is a group header (like a folder) above its members.
    const grouped = {
      buses: [
        { id: "voices", name: "Voices" },
        { id: "empty", name: "Empty" },
      ],
      tracks: [
        { id: "anna", bus: "voices", clips: [] },
        { id: "music", bus: null, clips: [] },
        { id: "ville", bus: "voices", clips: [] },
        { id: "fx", clips: [] },
      ],
    };
    const layout = layoutRows(grouped, 48);
    assert.deepEqual(
      layout.rows.map((r) => [r.kind, r.id, r.top, r.index, r.bus ?? null]),
      [
        ["bus", "voices", 0, 0, "voices"],
        ["track", "anna", BUS_HEIGHT, 0, "voices"],
        ["track", "ville", BUS_HEIGHT + 48, 2, "voices"],
        ["track", "music", BUS_HEIGHT + 96, 1, null],
        ["track", "fx", BUS_HEIGHT + 144, 3, null],
        ["bus", "empty", BUS_HEIGHT + 192, 1, "empty"],
      ],
    );
    assert.equal(layout.rows.at(-1).members, 0, "an empty bus says so");
    assert.equal(layout.rows[0].members, 2);
  });

  test("lane height is clamped to 24..160", () => {
    assert.equal(clampLaneHeight(5), 24);
    assert.equal(clampLaneHeight(500), 160);
    assert.equal(clampLaneHeight(Number.NaN), DEFAULT_LANE);
    assert.equal(layoutRows(project, 9999).rows[1].top, 160);
  });

  test("rowAt finds the row at a content y, or none", () => {
    const layout = layoutRows(project, 48);
    assert.equal(rowAt(layout, 0).id, "t1");
    assert.equal(rowAt(layout, 47.9).id, "t1");
    assert.equal(rowAt(layout, 48).id, "t2");
    assert.equal(rowAt(layout, 100).id, "b1");
    assert.equal(rowAt(layout, 500), null);
    assert.equal(rowAt(layout, -1), null);
  });

  test("only rows in view are listed (virtualised)", () => {
    const many = {
      buses: [],
      tracks: Array.from({ length: 100 }, (_, i) => ({ id: `t${i}`, clips: [] })),
    };
    const layout = layoutRows(many, 48);
    const shown = visibleRows(layout, 48 * 50, 200);
    assert.deepEqual(
      shown.map((r) => r.id),
      ["t50", "t51", "t52", "t53", "t54"],
    );
    assert.equal(visibleRows(layout, 0, 0).length, 0);
  });

  test("projectEnd is the last clip end over all tracks", () => {
    assert.equal(clipEnd(project.tracks[0].clips[1]), 3000);
    assert.equal(projectEnd(project), 3000);
    assert.equal(projectEnd({ tracks: [], buses: [] }), 0);
  });
});

describe("hit testing", () => {
  const layout = layoutRows(project, 48);
  const laneY = (inLane, row = 0) => RULER_HEIGHT + row * 48 + inLane;

  test("the ruler is its own area and carries a frame", () => {
    const hit = hitTest({ layout, project, view, x: 100, y: 10 });
    assert.equal(hit.area, "ruler");
    assert.equal(hit.frame, 1000);
  });

  test("a click inside a clip names the clip and track", () => {
    const hit = hitTest({ layout, project, view, x: 150, y: laneY(30) });
    assert.equal(hit.area, "lane");
    assert.equal(hit.row.id, "t1");
    assert.equal(hit.clip.id, "c1");
    assert.equal(hit.edge, null);
    assert.equal(hit.frame, 1500);
  });

  test("near a clip's edge it names the edge", () => {
    const start = hitTest({ layout, project, view, x: 101, y: laneY(30) });
    assert.equal(start.clip.id, "c1");
    assert.equal(start.edge, "start");
    const end = hitTest({ layout, project, view, x: 199, y: laneY(30) });
    assert.equal(end.edge, "end");
    assert.equal(end.clip.id, "c1");
  });

  test("a gap and an empty lane hit no clip", () => {
    assert.equal(hitTest({ layout, project, view, x: 10, y: laneY(30) }).clip, null);
    const empty = hitTest({ layout, project, view, x: 150, y: laneY(30, 1) });
    assert.equal(empty.row.id, "t2");
    assert.equal(empty.clip, null);
  });

  test("a bus row hits no clip; below all rows is no row", () => {
    const bus = hitTest({ layout, project, view, x: 150, y: laneY(10, 2) });
    assert.equal(bus.row.kind, "bus");
    assert.equal(bus.clip, null);
    const below = hitTest({ layout, project, view, x: 150, y: 390 });
    assert.equal(below.area, "none");
  });

  test("vertical scroll moves the rows under the pointer", () => {
    const hit = hitTest({
      layout,
      project,
      view: { ...view, scrollY: 48 },
      x: 150,
      y: RULER_HEIGHT + 10,
    });
    assert.equal(hit.row.id, "t2");
  });

  test("an envelope point is hit within a few pixels", () => {
    const row = layout.rows[0];
    const clip = project.tracks[0].clips[0];
    // The point (source frame 1000) lies at timeline frame 1000 - 500 + 1000 = 1500, x = 150.
    const y = RULER_HEIGHT + row.top + dbToY(6, row.height);
    const hit = hitTest({ layout, project, view, x: 152, y: y + 2 });
    assert.equal(hit.clip.id, clip.id);
    assert.equal(hit.point, 0);
    assert.equal(hitTest({ layout, project, view, x: 152, y: y + 30 }).point, null);
  });

  test("dB maps to y and back, with +12 at the top and the floor at the bottom", () => {
    assert.ok(dbToY(12, 48) < dbToY(0, 48));
    assert.ok(dbToY(0, 48) < dbToY(-30, 48));
    assert.ok(Math.abs(yToDb(dbToY(-7.5, 100), 100) + 7.5) < 1e-9);
    assert.equal(yToDb(-50, 48), 12, "clamped");
  });
});
