import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { followScroll } from "../follow.js";

const base = { zoom: 10, width: 1000, scroll: 0, playing: true, mode: "page", paused: false };

describe("following the playhead", () => {
  test("does nothing while the playhead is in view", () => {
    assert.deepEqual(followScroll({ ...base, playhead: 5000 }), { scroll: 0, paused: false });
  });

  test("page mode jumps a page when the playhead leaves the right edge", () => {
    const out = followScroll({ ...base, playhead: 10_500 });
    assert.equal(out.scroll, 10_500 - 0.1 * 1000 * 10);
    assert.equal(out.paused, false);
  });

  test("continuous mode keeps the playhead at the centre", () => {
    const out = followScroll({ ...base, mode: "continuous", scroll: 4000, playhead: 9500 });
    assert.equal(out.scroll, 9500 - 5000);
  });

  test("continuous mode does not scroll before the start", () => {
    assert.equal(followScroll({ ...base, mode: "continuous", playhead: 100 }).scroll, 0);
  });

  test("a stopped player is not followed", () => {
    const out = followScroll({ ...base, playing: false, playhead: 50_000 });
    assert.equal(out.scroll, 0);
  });

  test("scrolling by hand pauses following until the playhead is back in view", () => {
    const away = followScroll({ ...base, paused: true, scroll: 20_000, playhead: 5000 });
    assert.deepEqual(away, { scroll: 20_000, paused: true });
    const back = followScroll({ ...base, paused: true, scroll: 0, playhead: 5000 });
    assert.equal(back.paused, false);
  });

  test("a jump while stopped brings the playhead into view (Home, End, Tab)", () => {
    const end = followScroll({ ...base, playing: false, moved: true, playhead: 50_000 });
    assert.equal(end.scroll, 50_000 - 0.1 * 1000 * 10);
    const home = followScroll({
      ...base,
      playing: false,
      moved: true,
      scroll: 40_000,
      playhead: 0,
    });
    assert.equal(home.scroll, 0);
  });

  test("a jump to a place already in view does not scroll, nor does a stopped scroll by hand", () => {
    const seen = followScroll({ ...base, playing: false, moved: true, playhead: 5000 });
    assert.equal(seen.scroll, 0);
    const byHand = followScroll({
      ...base,
      playing: false,
      moved: false,
      scroll: 20_000,
      playhead: 0,
    });
    assert.equal(byHand.scroll, 20_000);
  });
});
