import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { previewRequest } from "../candidates-preview.js";

describe("previewRequest: one play request with the engine's skip list", () => {
  test("from, to and the skipped range become at, until and skip", () => {
    assert.deepEqual(previewRequest({ from: 100, to: 900, skip: [[300, 500]] }), {
      at: 100,
      until: 900,
      skip: [[300, 500]],
    });
  });
  test("several skipped pieces are passed in order; the engine merges and clips them", () => {
    assert.deepEqual(
      previewRequest({
        from: 0,
        to: 1000,
        skip: [
          [400, 600],
          [100, 200],
        ],
      }).skip,
      [
        [100, 200],
        [400, 600],
      ],
    );
  });
  test("frames are whole numbers", () => {
    assert.deepEqual(previewRequest({ from: 0.4, to: 500.6, skip: [[100.2, 200.7]] }), {
      at: 0,
      until: 501,
      skip: [[100, 201]],
    });
  });
  test("no skip: the whole stretch", () => {
    assert.deepEqual(previewRequest({ from: 5, to: 50, skip: [] }), {
      at: 5,
      until: 50,
      skip: [],
    });
    assert.deepEqual(previewRequest({ from: 5, to: 50 }).skip, []);
  });
  test("nothing to play: no request", () => {
    assert.equal(previewRequest(null), null);
    assert.equal(previewRequest({ from: 50, to: 50, skip: [] }), null);
    assert.equal(previewRequest({ from: 0, to: 500, skip: [[0, 500]] }), null);
    assert.equal(
      previewRequest({
        from: 0,
        to: 500,
        skip: [
          [0, 300],
          [250, 600],
        ],
      }),
      null,
    );
  });
});
