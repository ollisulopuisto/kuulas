import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { frameToTime, frameToX, xToFrame, zoomAround } from "../format.js";
import { setLanguageNow } from "../i18n.js";

describe("timeline frame math", () => {
  test("formats frames as locale-aware timecode", () => {
    setLanguageNow("en");
    assert.equal(frameToTime(60 * 48_000), "1:00.000");
    setLanguageNow("fi");
    assert.equal(frameToTime(60 * 48_000), "1:00,000");
    setLanguageNow("en");
  });

  test("converts frame and x using the left-edge scroll frame", () => {
    assert.equal(frameToX(1_000, 0, 100), 10);
    assert.equal(xToFrame(10, 0, 100), 1_000);
    assert.equal(frameToX(1_000, 500, 100), 5);
    assert.equal(xToFrame(5, 500, 100), 1_000);
  });

  test("zoom keeps its anchor at the same screen coordinate", () => {
    const next = zoomAround({ zoom: 100, scroll: 10_000, x: 200, nextZoom: 50 });
    assert.equal(frameToX(30_000, next.scroll, next.zoom), 200);
  });
});
