import assert from "node:assert/strict";
import { test } from "node:test";
import { initialTrackControlsState, transitionTrackControls } from "../track-controls-model.js";

test("hover opens a track controls flyout unless another track is pinned", () => {
  const open = transitionTrackControls(initialTrackControlsState(), {
    type: "open",
    trackId: "one",
  });
  assert.equal(open.openTrackId, "one");
  assert.equal(
    transitionTrackControls({ ...open, pinnedTrackId: "one" }, { type: "open", trackId: "two" })
      .openTrackId,
    "one",
  );
});

test("explicit toggle switches tracks and closes the current flyout", () => {
  const first = transitionTrackControls(initialTrackControlsState(), {
    type: "toggle",
    trackId: "one",
  });
  const second = transitionTrackControls(first, { type: "toggle", trackId: "two" });
  assert.deepEqual(second, { openTrackId: "two", pinnedTrackId: null });
  assert.deepEqual(
    transitionTrackControls(second, { type: "toggle", trackId: "two" }),
    initialTrackControlsState(),
  );
});

test("pin keeps its flyout open when the pointer leaves and blocks hover switches", () => {
  const pinned = transitionTrackControls(
    transitionTrackControls(initialTrackControlsState(), { type: "open", trackId: "one" }),
    { type: "pin", trackId: "one" },
  );
  assert.deepEqual(
    transitionTrackControls(pinned, {
      type: "leave",
      trackId: "one",
      pointerInside: false,
      focusInside: false,
    }),
    pinned,
  );
  assert.equal(
    transitionTrackControls(pinned, { type: "open", trackId: "two" }).openTrackId,
    "one",
  );
});

test("leaving closes only when pointer and focus both leave; Escape also unpins", () => {
  const open = { openTrackId: "one", pinnedTrackId: null };
  assert.deepEqual(
    transitionTrackControls(open, {
      type: "leave",
      trackId: "one",
      pointerInside: false,
      focusInside: true,
    }),
    open,
  );
  assert.deepEqual(
    transitionTrackControls(open, {
      type: "leave",
      trackId: "one",
      pointerInside: false,
      focusInside: false,
    }),
    initialTrackControlsState(),
  );
  assert.deepEqual(
    transitionTrackControls({ ...open, pinnedTrackId: "one" }, { type: "escape" }),
    initialTrackControlsState(),
  );
});

test("outside dismissal closes an unpinned flyout but preserves a pinned one", () => {
  const open = { openTrackId: "one", pinnedTrackId: null };
  assert.deepEqual(transitionTrackControls(open, { type: "outside" }), initialTrackControlsState());
  assert.deepEqual(
    transitionTrackControls({ ...open, pinnedTrackId: "one" }, { type: "outside" }),
    { openTrackId: "one", pinnedTrackId: "one" },
  );
});
