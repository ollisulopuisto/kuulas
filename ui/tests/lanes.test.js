import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  BUS_HEIGHT,
  clampLaneHeight,
  clipEnd,
  DEFAULT_LANE,
  dbToY,
  GROUP_GAP,
  hitTest,
  layoutFor,
  layoutRows,
  paintOrder,
  pointerIntent,
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
  test("tracks on no bus first; a gap; a bus with no tracks goes last", () => {
    const layout = layoutRows(project, 48);
    assert.deepEqual(
      layout.rows.map((r) => [r.kind, r.id, r.top, r.height]),
      [
        ["track", "t1", 0, 48],
        ["track", "t2", 48, 48],
        ["gap", "gap:2", 96, GROUP_GAP],
        ["bus", "b1", 96 + GROUP_GAP, BUS_HEIGHT],
      ],
    );
    assert.equal(layout.height, 96 + GROUP_GAP + BUS_HEIGHT);
  });

  test("a bus sits above its tracks, which gather under it; others keep their place", () => {
    // Owner, 2026-10-17: a bus is a group header (like a folder) above its
    // members; 2026-10-18: groups are separated by a gap of plain lane.
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
    const layout = layoutRows(grouped, 48, { busHeight: 30, groupGap: 10 });
    assert.deepEqual(
      layout.rows.map((r) => [r.kind, r.id, r.top, r.index ?? null, r.bus ?? null]),
      [
        ["bus", "voices", 0, 0, "voices"],
        ["track", "anna", 30, 0, "voices"],
        ["track", "ville", 78, 2, "voices"],
        ["gap", "gap:3", 126, null, null],
        ["track", "music", 136, 1, null],
        ["track", "fx", 184, 3, null],
        ["gap", "gap:6", 232, null, null],
        ["bus", "empty", 242, 1, "empty"],
      ],
    );
    assert.equal(layout.rows.at(-1).members, 0, "an empty bus says so");
    assert.equal(layout.rows[0].members, 2);
    assert.equal(layout.rows[2].last, true, "the last member ends the spine");
    assert.equal(layout.rows[1].last, false);
  });

  test("the editor merges one-track buses (owner decision, 2026-10-18)", () => {
    const state = {
      project: {
        buses: [{ id: "music", name: "Music" }],
        tracks: [{ id: "m", bus: "music", clips: [] }],
      },
      laneHeight: 80,
      busHeight: 32,
      groupGap: 14,
    };
    const rows = layoutFor(state).rows;
    assert.deepEqual(
      rows.map((r) => [r.kind, r.id, r.merged ?? false]),
      [["track", "m", true]],
    );
  });

  test("the bus row holds a name line and a level line, and is shorter than a lane", () => {
    assert.ok(BUS_HEIGHT >= 56);
    assert.ok(BUS_HEIGHT < DEFAULT_LANE);
  });

  test("a one-track bus can merge into its track's header (no bus row)", () => {
    const show = {
      buses: [
        { id: "voices", name: "Voices" },
        { id: "music", name: "Music" },
      ],
      tracks: [
        { id: "a", bus: "voices", clips: [] },
        { id: "b", bus: "voices", clips: [] },
        { id: "m", bus: "music", clips: [] },
      ],
    };
    const merged = layoutRows(show, 80, { busHeight: 32, groupGap: 14, mergeSingle: true });
    assert.deepEqual(
      merged.rows.map((r) => [r.kind, r.id, r.merged ?? false]),
      [
        ["bus", "voices", false],
        ["track", "a", false],
        ["track", "b", false],
        ["gap", "gap:3", false],
        ["track", "m", true],
      ],
    );
    const plain = layoutRows(show, 80, { busHeight: 32, groupGap: 14 });
    assert.equal(plain.height - merged.height, 32, "merging saves one bus row");
  });

  test("lane height is clamped to 24..360", () => {
    assert.equal(clampLaneHeight(5), 24);
    assert.equal(clampLaneHeight(500), 360);
    assert.equal(clampLaneHeight(Number.NaN), DEFAULT_LANE);
    assert.equal(layoutRows(project, 9999).rows[1].top, 360);
  });

  test("rowAt finds the row at a content y, or none", () => {
    const layout = layoutRows(project, 48);
    assert.equal(rowAt(layout, 0).id, "t1");
    assert.equal(rowAt(layout, 47.9).id, "t1");
    assert.equal(rowAt(layout, 48).id, "t2");
    assert.equal(rowAt(layout, 97).kind, "gap");
    assert.equal(rowAt(layout, 96 + GROUP_GAP + 1).id, "b1");
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

  test("a bus row, a group gap and the space below the last row are lane area", () => {
    const below = hitTest({ layout, project, view, x: 100, y: RULER_HEIGHT + layout.height + 50 });
    assert.equal(below.area, "lane");
    assert.equal(below.row, null);
    assert.equal(below.frame, 1000);
    const gap = hitTest({ layout, project, view, x: 100, y: RULER_HEIGHT + 96 + 2 });
    assert.equal(gap.area, "lane");
    assert.equal(gap.row.kind, "gap");
    const bus = hitTest({ layout, project, view, x: 100, y: RULER_HEIGHT + 96 + GROUP_GAP + 5 });
    assert.equal(bus.area, "lane");
    assert.equal(bus.row.kind, "bus");
  });

  test("the ruler is its own area and carries a frame", () => {
    const hit = hitTest({ layout, project, view, x: 100, y: 10 });
    assert.equal(hit.area, "ruler");
    assert.equal(hit.frame, 1000);
  });

  test("a track's ducking point under the pointer is autoPoint, whatever clip lies under it", () => {
    const ducked = {
      ...project,
      tracks: [
        {
          ...project.tracks[0],
          automation: [
            [1000, 0],
            [2000, -24],
          ],
        },
        ...project.tracks.slice(1),
      ],
    };
    const tall = layoutRows(ducked, 96);
    // 96 px lane: the band is 28 px high and ends 3 px above the bottom, so 0 dB sits at 65.
    const top = hitTest({ layout: tall, project: ducked, view, x: 100, y: RULER_HEIGHT + 65 });
    assert.equal(top.autoPoint, 0);
    const bottom = hitTest({ layout: tall, project: ducked, view, x: 200, y: RULER_HEIGHT + 93 });
    assert.equal(bottom.autoPoint, 1);
    const away = hitTest({ layout: tall, project: ducked, view, x: 150, y: RULER_HEIGHT + 10 });
    assert.equal(away.autoPoint, null);
    // A lane too short to draw the curve (under 40 px) has no points to hit.
    const short = layoutRows(ducked, 30);
    const none = hitTest({ layout: short, project: ducked, view, x: 100, y: RULER_HEIGHT + 20 });
    assert.equal(none.autoPoint, null);
  });

  test("a ruler hit names the marker under the pointer, if any", () => {
    const withMarker = {
      ...project,
      markers: [{ id: "m1", kind: "marker", name: "", start: 1000 }],
    };
    assert.equal(hitTest({ layout, project: withMarker, view, x: 100, y: 10 }).marker, "m1");
    assert.equal(hitTest({ layout, project: withMarker, view, x: 300, y: 10 }).marker, null);
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

  test("a bus row hits no clip; below all rows is lane area with no row", () => {
    // Was "none" until 2026-10-18; the owner's rule: a click anywhere in the
    // lane area sets the play cursor (pointerIntent).
    const bus = hitTest({ layout, project, view, x: 150, y: laneY(GROUP_GAP + 10, 2) });
    assert.equal(bus.row.kind, "bus");
    assert.equal(bus.clip, null);
    const below = hitTest({ layout, project, view, x: 150, y: 390 });
    assert.equal(below.area, "lane");
    assert.equal(below.row, null);
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

describe("what a click does (owner, 2026-10-18)", () => {
  const lane = (extra) => ({
    area: "lane",
    frame: 500,
    row: { kind: "bus" },
    clip: null,
    ...extra,
  });
  const clip = { id: "c1" };

  test("anywhere in the lane area sets the play cursor and clears the selection", () => {
    for (const row of [{ kind: "bus" }, { kind: "gap" }, { kind: "track" }, null]) {
      assert.deepEqual(pointerIntent(lane({ row }), {}), {
        seek: 500,
        selection: "clear",
        clip: null,
      });
    }
  });

  test("on a clip it also selects the clip", () => {
    assert.deepEqual(pointerIntent(lane({ row: { kind: "track" }, clip }), {}), {
      seek: 500,
      selection: "replace",
      clip,
    });
  });

  test("Shift+click only toggles the selection; it never moves the cursor", () => {
    assert.deepEqual(pointerIntent(lane({ clip }), { shift: true }), {
      seek: null,
      selection: "toggle",
      clip,
    });
    assert.deepEqual(pointerIntent(lane({}), { shift: true }), {
      seek: null,
      selection: "keep",
      clip: null,
    });
  });

  test("Mod+click toggles one clip in or out of the selection, without moving the cursor", () => {
    assert.deepEqual(pointerIntent(lane({ clip }), { mod: true }), {
      seek: null,
      selection: "toggle",
      clip,
    });
    assert.deepEqual(pointerIntent(lane({}), { mod: true }), {
      seek: null,
      selection: "keep",
      clip: null,
    });
  });

  test("the ruler seeks and keeps the selection; outside does nothing", () => {
    assert.deepEqual(pointerIntent({ area: "ruler", frame: 7 }, {}), {
      seek: 7,
      selection: "keep",
      clip: null,
    });
    assert.equal(pointerIntent({ area: "none", frame: 7 }, {}), null);
  });
});

describe("hit testing overlapping clips on one track", () => {
  const clipIn = (id, start, length) => ({
    id,
    start,
    offset: 0,
    length,
    gain_db: 0,
    envelope: [],
  });
  const layoutOf = (clips) => {
    const p = { rate: 48_000, buses: [], tracks: [{ id: "t1", clips }] };
    return { p, layout: layoutRows(p, 48) };
  };
  const at = (p, layout, frame) =>
    hitTest({
      layout,
      project: p,
      view,
      x: frame / view.zoom,
      y: RULER_HEIGHT + 24,
    });

  test("a short clip lying inside a long one is the one that gets clicked, whatever the order", () => {
    for (const clips of [
      [clipIn("long", 0, 3000), clipIn("short", 1000, 400)],
      [clipIn("short", 1000, 400), clipIn("long", 0, 3000)],
    ]) {
      const { p, layout } = layoutOf(clips);
      assert.equal(at(p, layout, 1200).clip.id, "short");
      // Outside the short one the long clip is still reachable.
      assert.equal(at(p, layout, 2500).clip.id, "long");
    }
  });

  test("two overlapping clips of one length: the later one in the list is on top", () => {
    const { p, layout } = layoutOf([clipIn("a", 0, 1000), clipIn("b", 500, 1000)]);
    assert.equal(at(p, layout, 700).clip.id, "b");
  });
});

describe("hitTest on a gate band (WP44)", () => {
  const gated = {
    ...project,
    tracks: [{ ...project.tracks[0], gate: [[3000, 4000]] }, project.tracks[1]],
  };
  const at = (x, extra = {}) =>
    hitTest({
      layout: layoutFor({ project: gated, laneHeight: 48 }),
      project: gated,
      view: { ...view, ...extra },
      x,
      y: RULER_HEIGHT + 10,
    });

  test("names the track and range under the pointer", () => {
    assert.deepEqual(at(350).gate, { trackId: "t1", index: 0, range: [3000, 4000] });
  });
  test("nothing outside the band, or when gates are hidden", () => {
    assert.equal(at(100).gate, null);
    assert.equal(at(350, { showGates: false }).gate, null);
  });
  test("a clip under the band is still reported", () => {
    assert.equal(at(250).clip?.id, "c2");
    assert.ok(at(350).gate);
  });
});

describe("hit testing placeholders (WP43)", () => {
  const withPh = { ...project, placeholders: [{ id: "h1", track: "t2", start: 500, length: 400 }] };
  const layout = layoutRows(withPh, 48);
  const onT2 = RULER_HEIGHT + 48 + 20;

  test("names the placeholder under the pointer on its own track", () => {
    const hit = hitTest({ layout, project: withPh, view, x: 60, y: onT2 });
    assert.equal(hit.placeholder.id, "h1");
    assert.equal(hit.clip, null);
  });

  test("none beside it, on another track, or in a project without any", () => {
    assert.equal(hitTest({ layout, project: withPh, view, x: 20, y: onT2 }).placeholder, null);
    assert.equal(
      hitTest({ layout, project: withPh, view, x: 60, y: RULER_HEIGHT + 20 }).placeholder,
      null,
    );
    assert.equal(hitTest({ layout, project, view, x: 60, y: onT2 }).placeholder, null);
  });
});

describe("layoutRows with per-track heights", () => {
  const three = {
    buses: [{ id: "b1", name: "Voices" }],
    tracks: [
      { id: "t1", bus: "b1", clips: [] },
      { id: "t2", bus: "b1", clips: [] },
      { id: "t3", clips: [] },
    ],
  };
  const heightOf = (layout, id) => layout.rows.find((row) => row.id === id).height;
  const topOf = (layout, id) => layout.rows.find((row) => row.id === id).top;

  test("a track with its own height uses it; the others use the global one", () => {
    const layout = layoutRows(three, 80, { laneHeights: { t2: 120 } });
    assert.equal(heightOf(layout, "t1"), 80);
    assert.equal(heightOf(layout, "t2"), 120);
    assert.equal(heightOf(layout, "t3"), 80);
  });

  test("rows below stack on the taller lane and the total follows", () => {
    const plain = layoutRows(three, 80);
    const tall = layoutRows(three, 80, { laneHeights: { t1: 100 } });
    assert.equal(topOf(tall, "t2") - topOf(plain, "t2"), 20);
    assert.equal(tall.height - plain.height, 20);
  });

  test("own heights are clamped; unknown ids and junk values are ignored", () => {
    const layout = layoutRows(three, 80, { laneHeights: { t1: 9999, t2: 3, t3: "x", nope: 50 } });
    assert.equal(heightOf(layout, "t1"), 360);
    assert.equal(heightOf(layout, "t2"), 24);
    assert.equal(heightOf(layout, "t3"), 80);
  });

  test("a merged one-track bus lane takes its own height too", () => {
    const one = { buses: [{ id: "b1", name: "V" }], tracks: [{ id: "t1", bus: "b1", clips: [] }] };
    const layout = layoutRows(one, 80, { mergeSingle: true, laneHeights: { t1: 50 } });
    assert.equal(heightOf(layout, "t1"), 50);
  });

  test("layoutFor passes the state's laneHeights", () => {
    const layout = layoutFor({
      project: three,
      laneHeight: 80,
      busHeight: 32,
      groupGap: 14,
      laneHeights: { t3: 40 },
    });
    assert.equal(heightOf(layout, "t3"), 40);
  });
});

describe("paintOrder (overlapping clips)", () => {
  test("long clips first, short ones on top, ties in list order; the input is not changed", () => {
    const clips = [
      { id: "s", length: 100 },
      { id: "l", length: 900 },
      { id: "m1", length: 400 },
      { id: "m2", length: 400 },
    ];
    assert.deepEqual(
      paintOrder(clips).map((c) => c.id),
      ["l", "m1", "m2", "s"],
    );
    assert.deepEqual(
      clips.map((c) => c.id),
      ["s", "l", "m1", "m2"],
    );
  });
});
