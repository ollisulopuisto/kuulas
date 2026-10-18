import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  clipSpan,
  createSourceMaps,
  neighbourClip,
  otherClips,
  partOf,
  segments,
  summaryText,
  totalFlicks,
  usedPercent,
} from "../source-map.js";

const map = {
  clips: [
    ["t1", "c1", 0, 40, false],
    ["t2", "c2", 50, 70, false],
    ["t1", "c3", 70, 90, true],
  ],
  used: [
    [0, 40],
    [50, 70],
  ],
  cut: [[70, 90]],
  unused: [
    [40, 50],
    [90, 100],
  ],
  parts: { c1: [1, 3], c2: [2, 3], c3: [3, 3] },
};

describe("source map numbers", () => {
  test("total, used percent, segments in percent and order", () => {
    assert.equal(totalFlicks(map), 100);
    assert.equal(usedPercent(map), 60);
    const out = segments(map);
    assert.deepEqual(
      out.map((s) => [s.kind, s.left, s.width]),
      [
        ["used", 0, 40],
        ["unused", 40, 10],
        ["used", 50, 20],
        ["cut", 70, 20],
        ["unused", 90, 10],
      ],
    );
  });

  test("an empty or missing map is harmless", () => {
    assert.equal(totalFlicks(null), 0);
    assert.equal(usedPercent({ used: [], cut: [], unused: [] }), 0);
    assert.deepEqual(segments(undefined), []);
    assert.equal(clipSpan(map, "gone"), null);
    assert.equal(
      summaryText(null, () => "x"),
      "",
    );
  });

  test("the clip's own span and part", () => {
    assert.deepEqual(clipSpan(map, "c2"), { left: 50, width: 20 });
    assert.deepEqual(partOf(map, "c2"), { n: 2, of: 3 });
    assert.equal(partOf(map, "zz"), null);
  });

  test("the summary asks for percent and the number of parts", () => {
    const seen = [];
    summaryText(map, (key, values) => seen.push([key, values]));
    assert.deepEqual(seen, [["ui.inspector.source.summary", { percent: 60, count: 3 }]]);
  });

  test("other clips leave this one out and stay in source order", () => {
    const rows = otherClips(map, "c2");
    assert.deepEqual(
      rows.map((r) => [r.clip, r.track, r.n, r.of, r.muted]),
      [
        ["c1", "t1", 1, 3, false],
        ["c3", "t1", 3, 3, true],
      ],
    );
  });

  test("next and previous clip by source position", () => {
    assert.equal(neighbourClip(map, "c2", 1), "c3");
    assert.equal(neighbourClip(map, "c2", -1), "c1");
    assert.equal(neighbourClip(map, "c1", -1), null);
    assert.equal(neighbourClip(map, "c3", 1), null);
    assert.equal(neighbourClip(map, "zz", 1), null);
  });
});

describe("source map fetcher", () => {
  function setup() {
    const calls = [];
    let changes = 0;
    const maps = createSourceMaps({
      fetchMap: (sha, signal) =>
        new Promise((resolve, reject) => {
          const call = { sha, signal, resolve, reject };
          signal.addEventListener("abort", () =>
            reject(Object.assign(new Error("x"), { name: "AbortError" })),
          );
          calls.push(call);
        }),
      onChange: () => {
        changes++;
      },
    });
    return { maps, calls, changes: () => changes };
  }
  const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

  test("caches by recording and head; asking again does not fetch", async () => {
    const { maps, calls, changes } = setup();
    maps.want("a", 5);
    maps.want("a", 5);
    assert.equal(calls.length, 1);
    assert.equal(maps.get("a", 5), null);
    calls[0].resolve(map);
    await tick();
    assert.equal(maps.get("a", 5), map);
    assert.equal(changes(), 1);
    maps.want("b", 5);
    maps.want("a", 5);
    assert.equal(calls.length, 2, "a is cached, so going back costs nothing");
    assert.equal(calls[1].signal.aborted, true, "the request for b was cancelled");
    maps.want("a", 6);
    assert.equal(calls.length, 3, "a new head is a new key");
  });

  test("a stale answer is ignored", async () => {
    const { maps, calls, changes } = setup();
    maps.want("a", 1);
    maps.want("b", 1);
    calls[0].resolve({ ...map, stale: true });
    await tick();
    assert.equal(maps.get("a", 1), null);
    assert.equal(changes(), 0);
    calls[1].resolve(map);
    await tick();
    assert.equal(maps.get("b", 1), map);
  });

  test("no recording cancels", () => {
    const { maps, calls } = setup();
    maps.want("a", 1);
    maps.want("", 1);
    assert.equal(calls[0].signal.aborted, true);
  });
});
