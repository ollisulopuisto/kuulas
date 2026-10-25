import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { headInView, liveFollowScroll } from "../live-follow.js";

const view = { scroll: 0, zoom: 100, width: 1000 }; // frames 0..100000 visible

describe("liveFollowScroll: the view follows the take's head until you steer away", () => {
  test("the head inside the view: nothing to do", () => {
    assert.equal(liveFollowScroll({ ...view, head: 50000, wasInView: true }), null);
  });

  test("the head runs off the right edge while you were watching it: a page forward", () => {
    // 10 % margin before the head, as playback does
    assert.equal(liveFollowScroll({ ...view, head: 100000, wasInView: true }), 90000);
  });

  test("you had scrolled away: the view is left where you put it", () => {
    assert.equal(liveFollowScroll({ ...view, head: 200000, wasInView: false }), null);
  });

  test("the head is behind the view (you scrolled right): left alone", () => {
    assert.equal(
      liveFollowScroll({ scroll: 300000, zoom: 100, width: 1000, head: 50000, wasInView: true }),
      null,
    );
  });
});

describe("headInView", () => {
  test("inside, at the left edge, and past the right edge", () => {
    assert.equal(headInView({ ...view, head: 0 }), true);
    assert.equal(headInView({ ...view, head: 99999 }), true);
    assert.equal(headInView({ ...view, head: 100000 }), false);
  });
});
