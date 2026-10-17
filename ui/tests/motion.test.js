// The motion language (owner, 2026-10-18): one setting turns every cue into
// a full animation, a subtle one, or a static highlight with the same meaning.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { CUES, cueFor, MOTION_MODES, motionMode } from "../motion.js";

describe("motionMode", () => {
  test("default full; the OS asking for reduced motion makes the default off", () => {
    assert.deepEqual(MOTION_MODES, ["full", "subtle", "off"]);
    assert.equal(motionMode(null, false), "full");
    assert.equal(motionMode(null, true), "off");
  });

  test("an explicit choice wins over the OS; junk falls back to the default", () => {
    assert.equal(motionMode("subtle", true), "subtle");
    assert.equal(motionMode("off", false), "off");
    assert.equal(motionMode("wobbly", false), "full");
  });
});

describe("cueFor", () => {
  test("every cue has a duration token, an easing token and a static fallback", () => {
    for (const [name, cue] of Object.entries(CUES)) {
      assert.match(cue.duration, /^--dur-/, name);
      assert.match(cue.easing, /^--ease-/, name);
      assert.ok(cue.still.length > 10, `${name} needs a static alternative`);
      assert.ok(cue.ms >= 90 && cue.ms <= 600, `${name}: ${cue.ms} ms is not gentle`);
    }
  });

  test("full animates, subtle shortens and drops movement, off gives the still highlight", () => {
    const full = cueFor("undo-flash", "full");
    assert.equal(full.animate, true);
    const subtle = cueFor("ripple-close", "subtle");
    assert.equal(subtle.animate, true);
    assert.equal(subtle.move, false, "subtle never moves things, only fades");
    assert.ok(subtle.ms < CUES["ripple-close"].ms);
    const off = cueFor("undo-flash", "off");
    assert.equal(off.animate, false);
    assert.equal(off.still, CUES["undo-flash"].still);
  });

  test("nothing animates while playing except the playhead", () => {
    assert.equal(cueFor("candidate-pulse", "full", { playing: true }).animate, false);
    assert.equal(cueFor("playhead-ease", "full", { playing: true }).animate, false);
  });

  test("an unknown cue is a still no-op", () => {
    assert.deepEqual(cueFor("nope", "full"), { animate: false, move: false, ms: 0, still: "" });
  });
});
