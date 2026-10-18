import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { cycleKindPlan, laneMates, nextKind, speakerArgs, speakerKey } from "../track-kind.js";

const project = {
  tracks: [
    { id: "A", name: "Anna", kind: "speech", speaker: "" },
    { id: "B", name: "Anna 2", kind: "speech", speaker: "Anna" },
    { id: "M", name: "Bed", kind: "music", speaker: "" },
  ],
};
const state = (extra = {}) => ({ project, focusTrack: "A", focusBus: null, ...extra });

describe("kind cycle", () => {
  test("speech -> music -> speech", () => {
    assert.equal(nextKind("speech"), "music");
    assert.equal(nextKind("music"), "speech");
  });
  test("a leftover speech-mix restarts at speech", () => {
    assert.equal(nextKind("speech-mix"), "speech");
  });
  test("an unknown kind restarts at speech", () => {
    assert.equal(nextKind("weird"), "speech");
  });
});

describe("cycleKindPlan", () => {
  test("one set_track edit for the focused track, with a toast naming the new kind", () => {
    const plan = cycleKindPlan(state());
    assert.equal(plan.op, "set_track");
    assert.deepEqual(plan.args, { track_id: "A", kind: "music" });
    assert.deepEqual(plan.label, { key: "ui.edit.label.track_kind" });
    assert.equal(plan.toast.key, "ui.edit.toast.track_kind.music");
    assert.deepEqual(plan.toast.values, { name: "Anna" });
  });
  test("music wraps to speech", () => {
    const plan = cycleKindPlan(state({ focusTrack: "M" }));
    assert.deepEqual(plan.args, { track_id: "M", kind: "speech" });
  });
  test("no focused track, nothing to do", () => {
    assert.equal(cycleKindPlan(state({ focusTrack: null })), null);
    assert.equal(cycleKindPlan({ project: null }), null);
  });
});

describe("speaker", () => {
  test("blank speaker means the track's own name", () => {
    assert.equal(speakerKey(project.tracks[0]), "Anna");
    assert.equal(speakerKey(project.tracks[1]), "Anna");
    assert.equal(speakerKey({ name: "X", speaker: "  " }), "X");
  });
  test("tracks sharing a speaker are lane mates, music excluded", () => {
    assert.deepEqual(
      laneMates(project, "A").map((t) => t.id),
      ["B"],
    );
    assert.deepEqual(laneMates(project, "M"), []);
  });
  test("typing nothing or the track's own name stores a blank speaker", () => {
    assert.deepEqual(speakerArgs(project.tracks[0], "  "), { track_id: "A", speaker: "" });
    assert.deepEqual(speakerArgs(project.tracks[0], "Anna"), { track_id: "A", speaker: "" });
    assert.deepEqual(speakerArgs(project.tracks[0], " Bob "), { track_id: "A", speaker: "Bob" });
  });
});
