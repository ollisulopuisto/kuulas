import assert from "node:assert/strict";
import { test } from "node:test";
import { busSoloTarget } from "../bus-solo.js";

const tracks = (solo = []) => [
  { id: "a", bus: "bus", solo: solo.includes("a") },
  { id: "b", bus: "bus", solo: solo.includes("b") },
  { id: "c", bus: null, solo: solo.includes("c") },
];
test("bus solo selects members exclusively, then clears on a second click", () => {
  assert.deepEqual(busSoloTarget(tracks(["c"]), "bus"), ["a", "b"]);
  assert.deepEqual(busSoloTarget(tracks(["a", "b"]), "bus"), []);
  assert.deepEqual(busSoloTarget(tracks(["a", "b", "c"]), "bus"), ["a", "b"]);
});
test("shift bus solo adds or removes the group without changing others", () => {
  assert.deepEqual(busSoloTarget(tracks(["c"]), "bus", true), ["a", "b", "c"]);
  assert.deepEqual(busSoloTarget(tracks(["a", "b", "c"]), "bus", true), ["c"]);
});
test("partial and empty bus solo are deterministic", () => {
  assert.deepEqual(busSoloTarget(tracks(["a"]), "bus"), ["a", "b"]);
  assert.deepEqual(busSoloTarget(tracks(["c"]), "empty"), ["c"]);
});
