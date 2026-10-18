import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { MOVE_STRIP_PX } from "../clip-drag.js";
import { DRAG_MODES, dragIntent, dragModeChoice, nextDragMode } from "../drag-mode.js";

const track = { kind: "track" };
const onClip = { area: "lane", row: track, clip: { id: "c" }, edge: null, point: null };
const onLane = { area: "lane", row: track, clip: null, edge: null, point: null };
const press = (extra = {}) => ({
  hit: onClip,
  rowY: 60,
  shift: false,
  alt: false,
  mod: false,
  ...extra,
});

describe("range mode: dragging paints a range (the default)", () => {
  const mode = "range";
  test("a plain drag on a clip's waveform paints a range", () => {
    assert.equal(dragIntent({ mode, ...press() }), "range");
  });
  test("a drag on the clip's label strip moves it", () => {
    assert.equal(dragIntent({ mode, ...press({ rowY: 4 }) }), "move");
    assert.equal(dragIntent({ mode, ...press({ rowY: MOVE_STRIP_PX }) }), "range");
  });
  test("Cmd (or Ctrl) held moves the clip from anywhere on it", () => {
    assert.equal(dragIntent({ mode, ...press({ mod: true }) }), "move");
  });
  test("Shift and Alt keep painting (Alt turns it into the clips it touches)", () => {
    assert.equal(dragIntent({ mode, ...press({ shift: true }) }), "range");
    assert.equal(dragIntent({ mode, ...press({ alt: true }) }), "range");
  });
  test("empty lane space paints a range", () => {
    assert.equal(dragIntent({ mode, ...press({ hit: onLane }) }), "range");
  });
});

describe("move mode: dragging moves a clip (Hindenburg's way)", () => {
  const mode = "move";
  test("a plain drag on a clip moves it, Shift or Alt paint a range", () => {
    assert.equal(dragIntent({ mode, ...press() }), "move");
    assert.equal(dragIntent({ mode, ...press({ shift: true }) }), "range");
    assert.equal(dragIntent({ mode, ...press({ alt: true }) }), "range");
  });
  test("empty lane space still paints a range", () => {
    assert.equal(dragIntent({ mode, ...press({ hit: onLane }) }), "range");
  });
});

describe("what neither mode drags", () => {
  test("edges, envelope points, the ruler and bus rows start no move or range", () => {
    for (const mode of DRAG_MODES) {
      assert.equal(dragIntent({ mode, ...press({ hit: { ...onClip, edge: "end" } }) }), null);
      assert.equal(dragIntent({ mode, ...press({ hit: { ...onClip, point: 0 } }) }), null);
      assert.equal(dragIntent({ mode, ...press({ hit: { area: "ruler", row: null } }) }), null);
      assert.equal(
        dragIntent({ mode, ...press({ hit: { ...onLane, row: { kind: "bus" } } }) }),
        null,
      );
    }
  });
});

describe("the preference", () => {
  test("a stored value that is a mode is used, anything else is the default (range)", () => {
    assert.equal(dragModeChoice("move"), "move");
    assert.equal(dragModeChoice("range"), "range");
    assert.equal(dragModeChoice("nope"), "range");
    assert.equal(dragModeChoice(null), "range");
  });
  test("the toggle goes to the other mode", () => {
    assert.equal(nextDragMode("range"), "move");
    assert.equal(nextDragMode("move"), "range");
  });
});
