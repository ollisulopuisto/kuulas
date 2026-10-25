import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createDragSnap } from "../drag-snap.js";

const project = {
  tracks: [
    {
      id: "A",
      automation: [
        [300, 0],
        [320, -9],
      ],
      gate: [[500, 600]],
      clips: [
        {
          id: "trim",
          start: 0,
          length: 1000,
          envelope: [
            [100, 0],
            [120, -6],
          ],
        },
        {
          id: "other",
          start: 800,
          length: 100,
          envelope: [
            [10, 0],
            [30, -6],
          ],
        },
      ],
    },
  ],
};
const marks = { playhead: 305, inPoint: 505, outPoint: 605 };

for (const [kind, excluded] of [
  ["edge trim", ["trim"]],
  ["clipboard drop", []],
]) {
  describe(`${kind} snap targets`, () => {
    const setup = () =>
      createDragSnap(project, excluded, marks, {
        primaryWithoutModifier: kind !== "edge trim",
      });
    test("modifier off leaves automation targets and marks absent", () => {
      const snap = setup();
      snap.update({ mod: false, alt: false });
      assert.deepEqual(snap.marks, []);
      assert.equal(snap.snap({ moved: [{ start: 0, end: 0 }], delta: 320, zoom: 1 }).at, null);
    });
    if (kind === "edge trim") {
      test("without the key edge trimming retains its unsnapped frame near primary targets", () => {
        const snap = setup();
        snap.update({ mod: false, alt: false });
        assert.deepEqual(snap.snap({ moved: [{ start: 0, end: 0 }], delta: 304, zoom: 1 }), {
          delta: 304,
          at: null,
        });
      });
    }
    test("modifier held adds track, gate and other envelope targets", () => {
      const snap = setup();
      snap.update({ mod: true, alt: false });
      assert.deepEqual(
        snap.marks,
        excluded.length ? [300, 320, 500, 600, 810, 830] : [100, 120, 300, 320, 500, 600, 810, 830],
      );
      assert.equal(snap.snap({ moved: [{ start: 0, end: 0 }], delta: 319, zoom: 1 }).at, 320);
      snap.update({ mod: false, alt: false });
      assert.deepEqual(snap.marks, []);
      assert.equal(snap.snap({ moved: [{ start: 0, end: 0 }], delta: 319, zoom: 1 }).at, null);
    });
    test("clip edges, playhead and marks beat a nearer automation point", () => {
      const snap = setup();
      snap.update({ mod: true, alt: false });
      for (const [delta, expected] of [
        [301, 305],
        [501, 505],
        [601, 605],
        [808, 800],
      ]) {
        assert.equal(snap.snap({ moved: [{ start: 0, end: 0 }], delta, zoom: 1 }).at, expected);
      }
    });
    test("Alt disables all snapping and hides automation marks", () => {
      const snap = setup();
      snap.update({ mod: true, alt: true });
      assert.deepEqual(snap.marks, []);
      assert.deepEqual(snap.snap({ moved: [{ start: 0, end: 0 }], delta: 301, zoom: 1 }), {
        delta: 301,
        at: null,
      });
    });
    for (const ending of ["release", "cancel (Esc)"]) {
      test(`${ending} clears the marks list`, () => {
        const snap = setup();
        snap.update({ mod: true, alt: false });
        assert.ok(snap.marks.length);
        snap.end();
        assert.deepEqual(snap.marks, []);
      });
    }
  });
}
