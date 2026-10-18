import assert from "node:assert/strict";
import test from "node:test";
import { enterFocus, focusLayout, focusSet, leaveFocus, walkFocus } from "../focus-layout.js";

test("focusSet: speaker expansion, empty speaker, unknown id", () => {
  const tracks = [
    { id: "t1", speaker: "Alice" },
    { id: "t2", speaker: "Bob" },
    { id: "t3", speaker: "Alice" },
    { id: "t4", speaker: "" },
    { id: "t5" },
  ];

  // Speaker expansion
  assert.deepEqual(focusSet(tracks, "t1"), ["t1", "t3"]);
  assert.deepEqual(focusSet(tracks, "t3"), ["t1", "t3"]);

  // Empty speaker or missing speaker focuses single track
  assert.deepEqual(focusSet(tracks, "t4"), ["t4"]);
  assert.deepEqual(focusSet(tracks, "t5"), ["t5"]);

  // Unknown id returns empty list
  assert.deepEqual(focusSet(tracks, "unknown"), []);
});

test("focusLayout: no focus equal split, clamped to min/max", () => {
  const tracks = [{ id: "t1" }, { id: "t2" }, { id: "t3" }];

  // 300 available, 3 tracks -> 100 each
  const res = focusLayout(tracks, null, { available: 300 });
  assert.deepEqual(res.heights, { t1: 100, t2: 100, t3: 100 });
  assert.equal(res.total, 300);

  // Clamped to min: available 60 -> floor(60/3)=20 < min(28) -> 28 each, total 84 > available
  const resMin = focusLayout(tracks, [], { available: 60, min: 28 });
  assert.deepEqual(resMin.heights, { t1: 28, t2: 28, t3: 28 });
  assert.equal(resMin.total, 84);

  // Clamped to max: available 1500 -> floor(1500/3)=500 > max(400) -> 400 each
  const resMax = focusLayout(tracks, [], { available: 1500, max: 400 });
  assert.deepEqual(resMax.heights, { t1: 400, t2: 400, t3: 400 });
  assert.equal(resMax.total, 1200);

  // Empty tracks
  assert.deepEqual(focusLayout([], null, { available: 300 }), {
    heights: {},
    total: 0,
  });
});

test("focusLayout: strip heights of 16 and focused tracks sharing with remainder", () => {
  const tracks = [
    { id: "t1", speaker: "Alice" },
    { id: "t2", speaker: "Bob" },
    { id: "t3", speaker: "Alice" },
    { id: "t4", speaker: "Charlie" },
  ];

  // Focus t1 and t3. Non-focused: t2, t4 (2 tracks).
  // strip = 16 -> non-focused total = 32.
  // available = 201 -> space for focused = 201 - 32 = 169.
  // 169 / 2 = 84 remainder 1 -> first gets 85, second gets 84.
  const res = focusLayout(tracks, ["t1", "t3"], { available: 201, strip: 16 });
  assert.deepEqual(res.heights, {
    t1: 85,
    t2: 16,
    t3: 84,
    t4: 16,
  });
  assert.equal(res.total, 201);
  assert(res.total <= 201);
});

test("focusLayout: min and max clamps on focused tracks", () => {
  const tracks = [{ id: "t1" }, { id: "t2" }, { id: "t3" }];

  // Focus t1. Non-focused t2, t3 -> 2 * 16 = 32.
  // available 40 -> space = 8 < min 28.
  // Focused track t1 gets min 28. Non-focused get 16. Total = 28 + 32 = 60 > 40.
  const resMin = focusLayout(tracks, ["t1"], {
    available: 40,
    strip: 16,
    min: 28,
  });
  assert.deepEqual(resMin.heights, { t1: 28, t2: 16, t3: 16 });
  assert.equal(resMin.total, 60);

  // Focus t1. available 600. space = 600 - 32 = 568 > max 400.
  // t1 clamped to 400. Total = 400 + 32 = 432 <= 600.
  const resMax = focusLayout(tracks, ["t1"], {
    available: 600,
    strip: 16,
    max: 400,
  });
  assert.deepEqual(resMax.heights, { t1: 400, t2: 16, t3: 16 });
  assert.equal(resMax.total, 432);
});

test("walkFocus: walking in both directions and at the ends", () => {
  const tracks = [
    { id: "t1", speaker: "Alice" },
    { id: "t2", speaker: "Bob" },
    { id: "t3", speaker: "Alice" },
    { id: "t4", speaker: "Charlie" },
  ];

  // Focus on t2. walk +1 -> after t2 is t3 (speaker Alice) -> focusSet expands to ["t1", "t3"]
  assert.deepEqual(walkFocus(tracks, ["t2"], 1), ["t1", "t3"]);

  // Focus on ["t1", "t3"] (indices 0 and 2). Last is index 2.
  // walk +1 -> after index 2 is index 3 (t4) -> ["t4"]
  assert.deepEqual(walkFocus(tracks, ["t1", "t3"], 1), ["t4"]);

  // At the end: focus on t4 (index 3). walk +1 -> stays unchanged
  assert.deepEqual(walkFocus(tracks, ["t4"], 1), ["t4"]);

  // From ["t1", "t3"], first is index 0. walk -1 -> at start, stays unchanged
  assert.deepEqual(walkFocus(tracks, ["t1", "t3"], -1), ["t1", "t3"]);

  // From t4 (index 3). walk -1 -> index 2 (t3, Alice) -> ["t1", "t3"]
  assert.deepEqual(walkFocus(tracks, ["t4"], -1), ["t1", "t3"]);

  // From t2 (index 1). walk -1 -> index 0 (t1, Alice) -> ["t1", "t3"]
  assert.deepEqual(walkFocus(tracks, ["t2"], -1), ["t1", "t3"]);
});

test("enterFocus & leaveFocus: solo remember and restore round trip", () => {
  const tracks = [
    { id: "t1", speaker: "Alice" },
    { id: "t2", speaker: "Bob" },
  ];
  const initial = { focus: null, soloBefore: null };

  // enterFocus with soloSet (Shift+F)
  const state1 = enterFocus(initial, "t1", tracks, ["t2"]);
  assert.deepEqual(state1, {
    focus: ["t1"],
    soloBefore: ["t2"],
  });

  // leaveFocus restores soloBefore
  const resLeave = leaveFocus(state1);
  assert.deepEqual(resLeave, {
    state: { focus: null, soloBefore: null },
    restoreSolo: ["t2"],
  });

  // enterFocus without soloSet
  const state2 = enterFocus(initial, "t2", tracks, null);
  assert.deepEqual(state2, {
    focus: ["t2"],
    soloBefore: null,
  });

  const resLeave2 = leaveFocus(state2);
  assert.deepEqual(resLeave2, {
    state: { focus: null, soloBefore: null },
    restoreSolo: null,
  });
});

test("immutability of the inputs", () => {
  const tracks = Object.freeze([
    Object.freeze({ id: "t1", speaker: "Alice" }),
    Object.freeze({ id: "t2", speaker: "Bob" }),
  ]);
  const focus = Object.freeze(["t1"]);
  const soloSet = Object.freeze(["t2"]);
  const state = Object.freeze({
    focus: Object.freeze(["t1"]),
    soloBefore: Object.freeze(["t2"]),
  });

  // None of these should throw or modify the frozen inputs
  focusSet(tracks, "t1");
  focusLayout(tracks, focus, { available: 200 });
  walkFocus(tracks, focus, 1);
  const s = enterFocus(state, "t2", tracks, soloSet);
  assert.notEqual(s, state);
  assert.deepEqual(s.focus, ["t2"]);
  const l = leaveFocus(state);
  assert.notEqual(l.state, state);
  assert.deepEqual(l.restoreSolo, ["t2"]);
});
