import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { busMembers, busOptions, inspectorTarget, roleKey } from "../track-target.js";

const project = {
  buses: [
    { id: "b1", name: "Voices" },
    { id: "b2", name: "Music" },
    { id: "b3", name: "Empty" },
  ],
  tracks: [
    { id: "t1", kind: "speech", bus: "b1", clips: [{ id: "c1" }] },
    { id: "t2", kind: "speech", bus: "b1", clips: [] },
    { id: "t3", kind: "music", bus: "b2", clips: [{ id: "c3" }] },
    { id: "t4", kind: "speech-mix", bus: null, clips: [] },
  ],
};
const state = (extra) => ({ project, selection: new Set(), focusTrack: null, ...extra });

describe("inspectorTarget", () => {
  test("nothing current: no track or bus", () => {
    assert.deepEqual(inspectorTarget(state()), { track: null, bus: null });
    assert.deepEqual(inspectorTarget({ project: null, selection: new Set() }), {
      track: null,
      bus: null,
    });
  });

  test("the current track, with its bus letter when it is on one", () => {
    const target = inspectorTarget(state({ focusTrack: "t1" }));
    assert.equal(target.track.id, "t1");
    assert.equal(target.bus, null);
    assert.equal(target.trackBus.letter, "A");
    assert.equal(target.merged, false);
  });

  test("a track alone on its bus is merged: its bus is inspected too", () => {
    const target = inspectorTarget(state({ focusTrack: "t3" }));
    assert.equal(target.merged, true);
    assert.equal(target.trackBus.bus.id, "b2");
    assert.equal(target.trackBus.letter, "B");
  });

  test("a track on no bus", () => {
    const target = inspectorTarget(state({ focusTrack: "t4" }));
    assert.equal(target.trackBus, null);
    assert.equal(target.merged, false);
  });

  test("with a clip selected on another track the current track still wins", () => {
    assert.equal(
      inspectorTarget(state({ focusTrack: "t4", selection: new Set(["c1"]) })).track.id,
      "t4",
    );
  });

  test("with no current track the selected clip's track is shown", () => {
    assert.equal(inspectorTarget(state({ selection: new Set(["c3"]) })).track.id, "t3");
  });

  test("a current bus row shows the Bus section instead", () => {
    const target = inspectorTarget(state({ focusBus: "b1", focusTrack: "t1" }));
    assert.equal(target.track, null);
    assert.equal(target.bus.bus.id, "b1");
    assert.equal(target.bus.letter, "A");
    assert.equal(target.bus.members, 2);
  });

  test("a vanished track or bus gives nothing", () => {
    assert.deepEqual(inspectorTarget(state({ focusTrack: "gone" })), { track: null, bus: null });
    assert.deepEqual(inspectorTarget(state({ focusBus: "gone" })), { track: null, bus: null });
  });
});

describe("bus options and members", () => {
  test("No bus first, then every bus with its letter, even an empty one", () => {
    assert.deepEqual(busOptions(project), [
      { value: "", letter: "", name: "" },
      { value: "b1", letter: "A", name: "Voices" },
      { value: "b2", letter: "B", name: "Music" },
      { value: "b3", letter: "C", name: "Empty" },
    ]);
  });

  test("members are counted per bus", () => {
    assert.equal(busMembers(project, "b1"), 2);
    assert.equal(busMembers(project, "b3"), 0);
  });

  test("roles map to the existing kind labels", () => {
    assert.equal(roleKey("speech-mix"), "ui.track.kind.speech-mix");
    assert.equal(roleKey("music"), "ui.track.kind.music");
  });
});
