import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createTileStore } from "../tiles.js";

function setup(over = {}) {
  const fetches = [];
  let changes = 0;
  let clock = 0;
  const store = createTileStore({
    fetchTile: (media, level, tile) =>
      new Promise((resolve, reject) => fetches.push({ media, level, tile, resolve, reject })),
    onChange: () => {
      changes += 1;
    },
    now: () => clock,
    ...over,
  });
  return {
    store,
    fetches,
    changes: () => changes,
    tick: (ms) => {
      clock += ms;
    },
  };
}
const tile = (v) => Float32Array.of(v, v);
const settle = () => new Promise((r) => setImmediate(r));
const want = (i) => ({ media: "m", level: 256, tile: i });

describe("tile store (what the worker keeps)", () => {
  test("a wanted tile is fetched once, however often it is asked for", () => {
    const { store, fetches } = setup();
    store.want([want(0), want(0)]);
    store.want([want(0)]);
    assert.equal(fetches.length, 1);
  });

  test("lookup answers once the tile has arrived, and onChange tells the painter", async () => {
    const { store, fetches, changes } = setup();
    store.want([want(0)]);
    assert.equal(store.lookup("m", 256, 0), undefined);
    fetches[0].resolve(tile(1));
    await settle();
    assert.deepEqual(Array.from(store.lookup("m", 256, 0)), [1, 1]);
    assert.equal(changes(), 1);
  });

  test("no more than the limit are in flight; the rest wait their turn", async () => {
    const { store, fetches } = setup({ maxInflight: 2 });
    store.want([want(0), want(1), want(2), want(3)]);
    assert.equal(fetches.length, 2);
    fetches[0].resolve(tile(1));
    await settle();
    assert.equal(fetches.length, 3);
  });

  test("the oldest tiles go when the cache is full, the newest stay", async () => {
    const { store, fetches } = setup({ maxTiles: 2, maxInflight: 9 });
    store.want([want(0), want(1), want(2)]);
    for (const f of fetches) f.resolve(tile(f.tile));
    await settle();
    assert.equal(store.lookup("m", 256, 0), undefined);
    assert.ok(store.lookup("m", 256, 1));
    assert.ok(store.lookup("m", 256, 2));
  });

  test("a failed tile is retried later, not in a loop", async () => {
    const { store, fetches, tick } = setup({ retryMs: 5000 });
    store.want([want(0)]);
    fetches[0].reject(new Error("404"));
    await settle();
    store.want([want(0)]);
    assert.equal(fetches.length, 1, "not at once");
    tick(6000);
    store.want([want(0)]);
    assert.equal(fetches.length, 2);
  });
});
