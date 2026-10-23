import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { automationTargets, SIGNIFICANT_DB } from "../automation-snap.js";

const clip = (id, start, length, extra = {}) => ({ id, start, length, offset: 0, ...extra });

describe("automationTargets: frames worth snapping to while the modifier is held", () => {
  test("the ends of a duck ramp are targets, the points on its flat parts are not", () => {
    const project = {
      tracks: [
        {
          id: "m",
          clips: [],
          // down from 0 to -12 dB between 1000 and 1200, flat, then back up 3000-3200
          automation: [
            [0, 0],
            [1000, 0],
            [1200, -12],
            [2000, -12],
            [3000, -12],
            [3200, 0],
            [5000, 0],
          ],
        },
      ],
    };
    assert.deepEqual(automationTargets(project, []), [1000, 1200, 3000, 3200]);
  });

  test("a change smaller than the threshold is not a border", () => {
    const project = {
      tracks: [
        {
          id: "m",
          clips: [],
          automation: [
            [0, 0],
            [100, -1],
            [200, 0],
          ],
        },
      ],
    };
    assert.ok(SIGNIFICANT_DB > 1);
    assert.deepEqual(automationTargets(project, []), []);
  });

  test("the edges of closed (auto-silenced) stretches are targets", () => {
    const project = {
      tracks: [
        {
          id: "a",
          clips: [],
          gate: [
            [500, 900],
            [2000, 2600],
          ],
        },
      ],
    };
    assert.deepEqual(automationTargets(project, []), [500, 900, 2000, 2600]);
  });

  test("other clips' envelope points count at their place on the timeline", () => {
    const project = {
      tracks: [
        {
          id: "a",
          clips: [
            // start 1000, source offset 200: the point at source frame 700 is at 1500
            clip("c1", 1000, 2000, {
              offset: 200,
              envelope: [
                [200, 0],
                [700, -9],
                [900, -9],
              ],
            }),
          ],
        },
      ],
    };
    assert.deepEqual(automationTargets(project, []), [1000, 1500]);
  });

  test("the clips being moved do not snap to their own envelope", () => {
    const project = {
      tracks: [
        {
          id: "a",
          clips: [
            clip("c1", 0, 2000, {
              envelope: [
                [0, 0],
                [700, -9],
              ],
            }),
          ],
        },
      ],
    };
    assert.deepEqual(automationTargets(project, ["c1"]), []);
  });

  test("sorted and without duplicates across tracks", () => {
    const project = {
      tracks: [
        { id: "a", clips: [], gate: [[300, 500]] },
        { id: "b", clips: [], gate: [[500, 800]] },
      ],
    };
    assert.deepEqual(automationTargets(project, []), [300, 500, 800]);
  });

  test("an empty or missing project has no targets", () => {
    assert.deepEqual(automationTargets(null, []), []);
    assert.deepEqual(automationTargets({ tracks: [{ id: "a" }] }, []), []);
  });
});
