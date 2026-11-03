import assert from "node:assert/strict";
import { test } from "node:test";
import {
  initialTrackFlyoutState,
  openTrackFlyoutId,
  trackFlyoutReducer,
} from "../track-header-flyout.js";

const apply = (state, type, trackId = "track-a") => trackFlyoutReducer(state, { type, trackId });

test("track controls reveal on hover and close when pointer leaves", () => {
  let state = apply(initialTrackFlyoutState(), "hover");
  assert.equal(openTrackFlyoutId(state), "track-a");
  state = apply(state, "leave");
  assert.equal(openTrackFlyoutId(state), null);
});

test("track controls reveal while keyboard focus is in the header or flyout", () => {
  let state = apply(initialTrackFlyoutState(), "focus");
  assert.equal(openTrackFlyoutId(state), "track-a");
  state = apply(state, "blur");
  assert.equal(openTrackFlyoutId(state), null);
});

test("pinning keeps controls open after pointer leaves and toggles closed", () => {
  let state = apply(initialTrackFlyoutState(), "pin");
  state = apply(state, "hover");
  state = apply(state, "leave");
  assert.equal(openTrackFlyoutId(state), "track-a");
  state = apply(state, "pin");
  assert.equal(openTrackFlyoutId(state), null);
});

test("Escape closes a pinned or transient flyout", () => {
  let state = apply(initialTrackFlyoutState(), "pin");
  state = apply(state, "escape");
  assert.equal(openTrackFlyoutId(state), null);
});

test("the explicit pin belongs to only one track at a time", () => {
  let state = apply(initialTrackFlyoutState(), "pin", "track-a");
  state = apply(state, "pin", "track-b");
  assert.equal(openTrackFlyoutId(state), "track-b");
});
