import assert from "node:assert/strict";
import test from "node:test";
import { groupColourIndex, groupMembers, groupSpan, groupsOf } from "../group-badge.js";

test("groupMembers: input order, falsy group id, nonexistent group", () => {
  const clips = [
    { id: "c1", group: "g1" },
    { id: "c2", group: "g2" },
    { id: "c3", group: "g1" },
    { id: "c4" },
    { id: "c5", group: "" },
  ];

  assert.deepEqual(groupMembers(clips, "g1"), ["c1", "c3"]);
  assert.deepEqual(groupMembers(clips, "g2"), ["c2"]);
  assert.deepEqual(groupMembers(clips, "nonexistent"), []);
  assert.deepEqual(groupMembers(clips, ""), []);
  assert.deepEqual(groupMembers(clips, null), []);
  assert.deepEqual(groupMembers(clips, undefined), []);
  assert.deepEqual(groupMembers([], "g1"), []);
  assert.deepEqual(groupMembers(null, "g1"), []);
});

test("groupColourIndex: stable index 0..palette-1, falsy id gives -1, custom palette", () => {
  // Falsy id gives -1
  assert.equal(groupColourIndex(""), -1);
  assert.equal(groupColourIndex(null), -1);
  assert.equal(groupColourIndex(undefined), -1);

  // Same id gives the same index
  const idx1 = groupColourIndex("vox");
  const idx2 = groupColourIndex("vox");
  assert.equal(idx1, idx2);
  assert(idx1 >= 0 && idx1 < 6);

  // Index in range for various IDs
  for (const id of ["g1", "g2", "intro", "outro", "sfx", "music", "interview-1"]) {
    const idx = groupColourIndex(id);
    assert(idx >= 0 && idx < 6, `Expected 0..5 but got ${idx} for ${id}`);
  }

  // Custom palette size
  const idx10 = groupColourIndex("vox", 10);
  assert(idx10 >= 0 && idx10 < 10);

  const idx20 = groupColourIndex("drums", 3);
  assert(idx20 >= 0 && idx20 < 3);
});

test("groupSpan: start and start+length across members, null when none", () => {
  const clips = [
    { id: "c1", group: "g1", start: 100, length: 50 },
    { id: "c2", group: "g2", start: 200, length: 100 },
    { id: "c3", group: "g1", start: 80, length: 40 },
    { id: "c4", group: "g1", start: 120, length: 80 },
  ];

  // g1 members:
  // c1: 100..150
  // c3: 80..120
  // c4: 120..200
  // Span: start = 80, end = 200
  assert.deepEqual(groupSpan(clips, "g1"), { start: 80, end: 200 });

  // Single member g2
  assert.deepEqual(groupSpan(clips, "g2"), { start: 200, end: 300 });

  // Nonexistent or falsy group returns null
  assert.equal(groupSpan(clips, "nonexistent"), null);
  assert.equal(groupSpan(clips, ""), null);
  assert.equal(groupSpan(clips, null), null);
  assert.equal(groupSpan([], "g1"), null);
  assert.equal(groupSpan(null, "g1"), null);
});

test("groupsOf: map from group id to member ids, ungrouped left out, new Map", () => {
  const clips = [
    { id: "c1", group: "vox" },
    { id: "c2", group: "drums" },
    { id: "c3", group: "vox" },
    { id: "c4" },
    { id: "c5", group: "" },
    { id: "c6", group: "drums" },
  ];

  const map = groupsOf(clips);
  assert(map instanceof Map);
  assert.equal(map.size, 2);
  assert.deepEqual(map.get("vox"), ["c1", "c3"]);
  assert.deepEqual(map.get("drums"), ["c2", "c6"]);
  assert.equal(map.has(""), false);
  assert.equal(map.has(undefined), false);

  // Empty clips returns empty map
  const emptyMap = groupsOf([]);
  assert(emptyMap instanceof Map);
  assert.equal(emptyMap.size, 0);

  const nullMap = groupsOf(null);
  assert(nullMap instanceof Map);
  assert.equal(nullMap.size, 0);
});

test("immutability of inputs", () => {
  const clip1 = Object.freeze({
    id: "c1",
    group: "g1",
    start: 10,
    length: 20,
  });
  const clip2 = Object.freeze({
    id: "c2",
    group: "g1",
    start: 15,
    length: 30,
  });
  const clips = Object.freeze([clip1, clip2]);

  groupMembers(clips, "g1");
  groupColourIndex("g1");
  groupSpan(clips, "g1");
  const m1 = groupsOf(clips);
  const m2 = groupsOf(clips);
  assert.notEqual(m1, m2);
  assert.equal(clips.length, 2);
});
