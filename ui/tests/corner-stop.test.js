import assert from "node:assert/strict";
import test from "node:test";
import { cornerStopFace } from "../record-model.js";

const t = (key, args) => (args ? `${key}:${JSON.stringify(args)}` : key);

test("cornerStopFace: nothing recording -> null (the button stays Record)", () => {
  assert.equal(
    cornerStopFace({
      recording: false,
      stopping: false,
      view: { state: "idle" },
      mode: "click",
      t,
    }),
    null,
  );
});

test("cornerStopFace: recording, one-click mode -> the plain stop label", () => {
  const face = cornerStopFace({
    recording: true,
    stopping: false,
    view: { state: "idle" },
    mode: "click",
    t,
  });
  assert.equal(face.label, "ui.record.stop");
  assert.equal(face.state, "idle");
  assert.equal(face.disabled, false);
});

test("cornerStopFace: hold mode -> the hold label", () => {
  const face = cornerStopFace({
    recording: true,
    stopping: false,
    view: { state: "idle" },
    mode: "hold",
    t,
  });
  assert.equal(face.label, "ui.record.stop_hold");
});

test("cornerStopFace: confirming state carries the countdown label and state", () => {
  const face = cornerStopFace({
    recording: true,
    stopping: false,
    view: { state: "confirming", secondsLeft: 2 },
    mode: "confirm",
    t,
  });
  assert.equal(face.label, 'ui.record.stop_confirm:{"seconds":2}');
  assert.equal(face.state, "confirming");
});

test("cornerStopFace: stopping -> the stopping label, disabled", () => {
  const face = cornerStopFace({
    recording: true,
    stopping: true,
    view: { state: "idle" },
    mode: "click",
    t,
  });
  assert.equal(face.label, "ui.record.stopping");
  assert.equal(face.state, "stopped");
  assert.equal(face.disabled, true);
});
