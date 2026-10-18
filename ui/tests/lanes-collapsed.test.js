import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { layoutFor, layoutRows, rowAt } from "../lanes.js";

describe("collapsed buses", () => {
  const show = {
    buses: [
      { id: "voices", name: "Voices" },
      { id: "music", name: "Music" },
    ],
    tracks: [
      { id: "a", bus: "voices", clips: [] },
      { id: "b", bus: "voices", clips: [] },
      { id: "m", bus: "music", clips: [] },
      { id: "x", bus: null, clips: [] },
    ],
  };
  const opts = { busHeight: 32, groupGap: 14, mergeSingle: true };

  test("a collapsed bus keeps its row and hides its member tracks", () => {
    const layout = layoutRows(show, 80, { ...opts, collapsed: new Set(["voices"]) });
    assert.deepEqual(
      layout.rows.map((r) => [r.kind, r.id]),
      [
        ["bus", "voices"],
        ["gap", "gap:1"],
        ["track", "m"],
        ["gap", "gap:3"],
        ["track", "x"],
      ],
    );
    const bus = layout.rows[0];
    assert.equal(bus.collapsed, true);
    assert.equal(bus.members, 2);
    assert.deepEqual(bus.memberIndexes, [0, 1]);
  });

  test("expanded is the default; an expanded bus row says so", () => {
    const layout = layoutRows(show, 80, opts);
    assert.equal(layout.rows[0].collapsed, false);
    assert.equal(layout.rows.filter((r) => r.kind === "track").length, 4);
    const none = layoutRows(show, 80, { ...opts, collapsed: new Set() });
    assert.deepEqual(none.rows, layout.rows);
  });

  test("collapsing saves exactly the member lanes", () => {
    const open = layoutRows(show, 80, opts);
    const shut = layoutRows(show, 80, { ...opts, collapsed: new Set(["voices"]) });
    assert.equal(open.height - shut.height, 160);
    for (const row of shut.rows) assert.equal(rowAt(shut, row.top).id, row.id);
  });

  test("a merged one-track bus has no row to collapse: it stays as it is", () => {
    const open = layoutRows(show, 80, opts);
    const shut = layoutRows(show, 80, { ...opts, collapsed: new Set(["music"]) });
    assert.deepEqual(shut.rows, open.rows);
  });

  test("without merging, a one-track bus collapses too", () => {
    const shut = layoutRows(show, 80, {
      busHeight: 32,
      groupGap: 14,
      collapsed: new Set(["music"]),
    });
    assert.equal(
      shut.rows.some((r) => r.id === "m"),
      false,
    );
  });

  test("an unknown id in the set is ignored; an empty bus has nothing to hide", () => {
    const withEmpty = { ...show, buses: [...show.buses, { id: "e", name: "E" }] };
    const a = layoutRows(withEmpty, 80, opts);
    const b = layoutRows(withEmpty, 80, { ...opts, collapsed: new Set(["gone", "e"]) });
    assert.deepEqual(
      b.rows.map((r) => r.id),
      a.rows.map((r) => r.id),
    );
  });

  test("layoutFor passes the state's collapsedBuses", () => {
    const layout = layoutFor({
      project: show,
      laneHeight: 80,
      busHeight: 32,
      groupGap: 14,
      collapsedBuses: new Set(["voices"]),
    });
    assert.equal(
      layout.rows.some((r) => r.id === "a"),
      false,
    );
  });
});
