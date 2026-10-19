import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  DRAG_PX,
  edgeChange,
  edgeGhost,
  edgeLimits,
  ghostGeometry,
  isDrag,
  resolveEdge,
  touchingNeighbour,
} from "../edge-drag.js";
import { RULER_HEIGHT } from "../lanes.js";

const S = 48_000;
const project = {
  rate: S,
  media: [
    { id: "m1", frames: 10 * S },
    { id: "m2", frames: 10 * S },
  ],
  tracks: [
    {
      id: "A",
      clips: [
        { id: "a", media: "m1", start: 2 * S, offset: 2 * S, length: 4 * S },
        { id: "b", media: "m1", start: 6 * S, offset: 6 * S, length: 3 * S },
        { id: "z", media: "m1", start: 12 * S, offset: 0, length: S },
      ],
    },
    { id: "B", clips: [{ id: "d", media: "m2", start: 7 * S, offset: 0, length: 2 * S }] },
  ],
};
const track = project.tracks[0];
const [a, b] = track.clips;
const d = project.tracks[1].clips[0];

describe("isDrag", () => {
  test("4 px of travel in any direction starts a drag, less is a click", () => {
    assert.equal(DRAG_PX, 4);
    assert.equal(isDrag(0, 0), false);
    assert.equal(isDrag(3, 0), false);
    assert.equal(isDrag(4, 0), true);
    assert.equal(isDrag(-4, 0), true);
    assert.equal(isDrag(3, 3), true);
  });
});

describe("touchingNeighbour", () => {
  test("the clip on the same track that meets the edge exactly", () => {
    assert.equal(touchingNeighbour(track, a, "end"), b);
    assert.equal(touchingNeighbour(track, b, "start"), a);
  });
  test("nothing when there is a gap or the other side", () => {
    assert.equal(touchingNeighbour(track, a, "start"), null);
    assert.equal(touchingNeighbour(track, b, "end"), null);
    assert.equal(touchingNeighbour(project.tracks[1], d, "start"), null);
  });
});

describe("edgeLimits and resolveEdge", () => {
  test("roll with a neighbour: bounded by the neighbour's last frame", () => {
    const limits = edgeLimits(project, track, a, "end", { ripple: false });
    assert.equal(limits.low, 2 * S + 1);
    assert.equal(limits.high, 9 * S - 1);
    assert.equal(limits.neighbour, b);
  });
  test("roll start with a neighbour: bounded by the neighbour's first frame and the media", () => {
    const limits = edgeLimits(project, track, b, "start", { ripple: false });
    assert.equal(limits.low, 2 * S + 1);
    assert.equal(limits.high, 9 * S - 1);
  });
  test("roll into a gap stops at the next clip and at the media's end", () => {
    const limits = edgeLimits(project, track, b, "end", { ripple: false });
    assert.equal(limits.neighbour, null);
    assert.equal(limits.high, 10 * S); // media ends at 10 s; z starts at 12 s
    assert.equal(limits.low, 6 * S + 1);
  });
  test("a start edge cannot go before the media's first frame", () => {
    const limits = edgeLimits(project, project.tracks[1], d, "start", { ripple: false });
    assert.equal(limits.low, 7 * S);
    assert.equal(limits.high, 9 * S - 1);
  });
  test("a gap-extend does not run into the next clip on the track", () => {
    const extra = {
      ...project,
      tracks: [
        {
          id: "A",
          clips: [
            { id: "p", media: "m1", start: 0, offset: 0, length: S },
            { id: "q", media: "m1", start: 3 * S, offset: 3 * S, length: S },
          ],
        },
      ],
    };
    const [p] = extra.tracks[0].clips;
    assert.equal(edgeLimits(extra, extra.tracks[0], p, "end", { ripple: false }).high, 3 * S);
  });
  test("ripple ignores neighbours: only the clip's own media and one frame bound it", () => {
    const end = edgeLimits(project, track, a, "end", { ripple: true });
    assert.equal(end.neighbour, null);
    assert.equal(end.low, 2 * S + 1);
    assert.equal(end.high, 10 * S);
    const start = edgeLimits(project, track, a, "start", { ripple: true });
    assert.equal(start.low, 0);
    assert.equal(start.high, 6 * S - 1);
  });
  test("resolveEdge clamps the frame and rounds it", () => {
    assert.equal(resolveEdge(project, track, a, "end", 7.4 * S, { ripple: false }).frame, 7.4 * S);
    assert.equal(resolveEdge(project, track, a, "end", 99 * S, { ripple: false }).frame, 9 * S - 1);
    assert.equal(resolveEdge(project, track, a, "end", 0, { ripple: false }).frame, 2 * S + 1);
    assert.equal(resolveEdge(project, track, a, "end", 5.5, { ripple: true }).frame, 2 * S + 1);
  });
});

describe("edgeChange", () => {
  test("the op and its arguments: roll by default, ripple with Shift", () => {
    assert.deepEqual(edgeChange("a", "end", 7 * S, false), {
      op: "roll_trim",
      args: { clip_id: "a", edge: "end", frame: 7 * S },
      labelKey: "ui.edge.roll",
    });
    assert.deepEqual(edgeChange("a", "start", 3 * S, true), {
      op: "ripple_trim",
      args: { clip_id: "a", edge: "start", frame: 3 * S },
      labelKey: "ui.edge.ripple",
    });
  });
  test("a ripple with group editing on asks the other tracks to give material back too", () => {
    assert.deepEqual(edgeChange("a", "end", 7 * S, true, true).args, {
      clip_id: "a",
      edge: "end",
      frame: 7 * S,
      extend_partners: true,
    });
    // Roll never does, and neither does a ripple with group editing off.
    assert.equal(edgeChange("a", "end", 7 * S, false, true).args.extend_partners, undefined);
    assert.equal(edgeChange("a", "end", 7 * S, true, false).args.extend_partners, undefined);
  });
});

describe("edgeGhost", () => {
  test("roll end with a neighbour: both clips' new spans meet at the frame", () => {
    const ghost = edgeGhost(project, track, a, "end", 7 * S, { ripple: false });
    assert.equal(ghost.line, 7 * S);
    assert.deepEqual(ghost.clip, { start: 2 * S, end: 7 * S });
    assert.deepEqual(ghost.neighbour, { start: 7 * S, end: 9 * S });
    assert.equal(ghost.ripple, false);
  });
  test("roll start with a neighbour", () => {
    const ghost = edgeGhost(project, track, b, "start", 5 * S, { ripple: false });
    assert.deepEqual(ghost.clip, { start: 5 * S, end: 9 * S });
    assert.deepEqual(ghost.neighbour, { start: 2 * S, end: 5 * S });
  });
  test("roll into a gap has no neighbour", () => {
    const ghost = edgeGhost(project, track, b, "end", 9.5 * S, { ripple: false });
    assert.deepEqual(ghost.clip, { start: 6 * S, end: 9.5 * S });
    assert.equal(ghost.neighbour, null);
  });
  test("ripple end: no neighbour, the line is the new end", () => {
    const ghost = edgeGhost(project, track, a, "end", 5 * S, { ripple: true });
    assert.deepEqual(ghost.clip, { start: 2 * S, end: 5 * S });
    assert.equal(ghost.neighbour, null);
    assert.equal(ghost.line, 5 * S);
    assert.equal(ghost.ripple, true);
  });
  test("ripple start keeps the clip's start and shortens it by the dragged amount", () => {
    const ghost = edgeGhost(project, track, a, "start", 3 * S, { ripple: true });
    assert.deepEqual(ghost.clip, { start: 2 * S, end: 5 * S });
    assert.equal(ghost.line, 3 * S);
  });
  test("the frame is clamped like the op will clamp it", () => {
    const ghost = edgeGhost(project, track, a, "end", 99 * S, { ripple: false });
    assert.equal(ghost.line, 9 * S - 1);
  });
});

describe("ghostGeometry", () => {
  const view = { scroll: 0, zoom: 100, scrollY: 0 };
  const row = { top: 40, height: 80 };

  test("a thin line and the clip outline, in canvas pixels", () => {
    const ghost = edgeGhost(project, track, a, "end", 7 * S, { ripple: false });
    const g = ghostGeometry(ghost, { view, row });
    const y = RULER_HEIGHT + 40 + 2;
    assert.equal(g.clip.x, (2 * S) / 100);
    assert.equal(g.clip.w, (5 * S) / 100);
    assert.equal(g.clip.y, y);
    assert.equal(g.clip.h, 76);
    assert.equal(g.line.x, (7 * S) / 100);
    assert.equal(g.line.y, RULER_HEIGHT + 40);
    assert.equal(g.line.h, 80);
    assert.equal(g.neighbour.x, (7 * S) / 100);
    assert.equal(g.neighbour.w, (2 * S) / 100);
  });
  test("vertical scroll moves it, no neighbour gives null", () => {
    const ghost = edgeGhost(project, track, a, "end", 5 * S, { ripple: true });
    const g = ghostGeometry(ghost, { view: { ...view, scrollY: 10 }, row });
    assert.equal(g.line.y, RULER_HEIGHT + 30);
    assert.equal(g.neighbour, null);
  });
});

describe("an edge drag overwrites its neighbours (WP83)", () => {
  const S2 = S;
  const three = {
    rate: S,
    media: [{ id: "m", frames: 10 * S }],
    tracks: [
      {
        id: "T",
        clips: [
          { id: "c1", media: "m", start: 2 * S, offset: 2 * S, length: 2 * S },
          { id: "c2", media: "m", start: 4 * S, offset: 4 * S, length: S },
          { id: "c3", media: "m", start: 5 * S, offset: 5 * S, length: 4 * S },
        ],
      },
    ],
  };
  const tt = three.tracks[0];
  const [c1, c2, c3] = tt.clips;
  const on = { ripple: false, overwrite: true };

  test("extending the start leftwards is not stopped by the neighbours", () => {
    const limits = edgeLimits(three, tt, c3, "start", on);
    assert.equal(limits.low, 0);
    assert.equal(resolveEdge(three, tt, c3, "start", 3 * S, on).frame, 3 * S);
    assert.equal(resolveEdge(three, tt, c3, "start", -9 * S, on).frame, 0);
  });
  test("extending the end rightwards is bounded by the clip's own media", () => {
    assert.equal(resolveEdge(three, tt, c1, "end", 99 * S, on).frame, 10 * S);
  });
  test("with overwrite off the edge stops at the neighbour as before", () => {
    const off = { ripple: false, overwrite: false };
    assert.equal(resolveEdge(three, tt, c3, "start", 0, off).frame, 4 * S + 1);
  });
  test("shrinking an edge still rolls the neighbour", () => {
    const r = resolveEdge(three, tt, c3, "start", 7 * S, on);
    assert.equal(r.frame, 7 * S);
    assert.equal(r.neighbour, c2);
    const ghost = edgeGhost(three, tt, c3, "start", 7 * S, on);
    assert.deepEqual(ghost.neighbour, { start: 4 * S, end: 7 * S });
    assert.deepEqual(ghost.covered, []);
  });
  test("extending names what is trimmed and what is removed", () => {
    const ghost = edgeGhost(three, tt, c3, "start", 3 * S, on);
    assert.equal(ghost.neighbour, null);
    assert.deepEqual(ghost.region, { start: 3 * S, end: 5 * S });
    assert.deepEqual(ghost.covered, [
      { id: "c1", start: 2 * S, end: 4 * S, kept: { start: 2 * S, end: 3 * S } },
      { id: "c2", start: 4 * S, end: 5 * S, kept: null },
    ]);
  });
  test("covering the end of a clip keeps its front; the end edge trims the front of the next", () => {
    const ghost = edgeGhost(three, tt, c1, "end", 4.5 * S2, on);
    assert.deepEqual(ghost.covered, [
      { id: "c2", start: 4 * S, end: 5 * S, kept: { start: 4.5 * S2, end: 5 * S } },
    ]);
  });
  test("ripple and overwrite off cover nothing", () => {
    assert.deepEqual(
      edgeGhost(three, tt, c3, "start", 3 * S, { ripple: true, overwrite: true }).covered,
      [],
    );
    assert.deepEqual(
      edgeGhost(three, tt, c3, "start", 4.5 * S, { ripple: false, overwrite: false }).covered,
      [],
    );
  });
  test("the covered clips and the region get canvas boxes", () => {
    const view = { scroll: 0, zoom: 100, scrollY: 0 };
    const row = { top: 40, height: 80 };
    const g = ghostGeometry(edgeGhost(three, tt, c3, "start", 3 * S, on), { view, row });
    assert.equal(g.region.x, (3 * S) / 100);
    assert.equal(g.region.w, (2 * S) / 100);
    assert.equal(g.covered.length, 2);
    assert.equal(g.covered[1].x, (4 * S) / 100);
    assert.equal(g.covered[1].removed, true);
    assert.equal(g.covered[0].removed, false);
  });
  test("the edit carries overwrite=false only when Alt is held", () => {
    assert.equal(edgeChange("a", "end", 1, false, false, true).args.overwrite, undefined);
    assert.equal(edgeChange("a", "end", 1, false, false, false).args.overwrite, false);
  });
});
