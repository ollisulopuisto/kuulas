import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { setLanguageNow } from "../i18n.js";
import {
  frameToTime,
  frameToX,
  hitTestClip,
  hitTestLane,
  timeToFrame,
  zoomAround,
} from "../format.js";

describe("timeline frame math", () => {
  test("formats frames as locale-aware timecode", () => {
    setLanguageNow("en");
    assert.equal(frameToTime(60 * 48_000, "en"), "1:00.000");
    setLanguageNow("fi");
    assert.equal(frameToTime(60 * 48_000, "fi"), "1:00,000");
    setLanguageNow("en");
  });

  test("converts frame and x using the left-edge scroll frame", () => {
    assert.equal(frameToX(1_000, 0, 100), 10);
    assert.equal(timeToFrame(10, 0, 100), 1_000);
  });

  test("zoom keeps its anchor at the same screen coordinate", () => {
    const next = zoomAround({ zoom: 100, scroll: 10_000, x: 200, nextZoom: 50 });
    assert.equal(frameToX(30_000, next.scroll, next.zoom), 200);
  });

  test("hit testing resolves lane and clip ids and ignores misses", () => {
    const tracks = [{ id: "t1" }, { id: "t2" }];
    assert.equal(hitTestLane(60, 10, tracks, 48), "t2");
    assert.equal(hitTestLane(120, 10, tracks, 48), null);
    const clips = [{ id: "c1", track: "t1", start: 100, end: 200 }];
    assert.equal(hitTestClip(150, "t1", clips), "c1");
    assert.equal(hitTestClip(220, "t1", clips), null);
  });
});
