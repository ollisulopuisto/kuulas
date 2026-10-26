import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { anchorPatch, initialState, reduceLive, serverPatch } from "../store.js";

describe("a clipboard change from another window", () => {
  test("asks for the clipboard to be read again, and nothing else", () => {
    const out = reduceLive(initialState(), { type: "clipboard_changed" });
    assert.equal(out.clipboard, true);
    assert.equal(out.refresh, false);
    assert.deepEqual(out.patch, {});
  });
});

describe("client state", () => {
  test("holds the fields the plan lists, with selection a Set", () => {
    const s = initialState();
    for (const key of [
      "project",
      "head",
      "canUndo",
      "canRedo",
      "words",
      "selection",
      "focusTrack",
      "playhead",
      "inPoint",
      "outPoint",
      "zoom",
      "scroll",
      "playing",
    ]) {
      assert.ok(key in s, key);
    }
    assert.ok(s.selection instanceof Set);
  });

  test("a server answer maps to the client's names", () => {
    const patch = serverPatch({
      project: { tracks: [] },
      head: "h1",
      can_undo: true,
      can_redo: false,
      missing: [],
    });
    assert.deepEqual(patch, {
      project: { tracks: [] },
      head: "h1",
      canUndo: true,
      canRedo: false,
      missingMedia: new Set(),
      readOnly: null,
    });
  });

  test("a project held elsewhere carries who holds it; one you can edit clears it", () => {
    const note = { host: "Studio-Mac", user: "olli", opened_utc: "2026-10-23T11:05:00Z" };
    assert.deepEqual(serverPatch({ project: { tracks: [] }, read_only: note }).readOnly, note);
    assert.equal(serverPatch({ project: { tracks: [] } }).readOnly, null);
    assert.equal("readOnly" in serverPatch({ head: "h" }), false, "no project: unchanged");
  });

  test("the media whose file is missing become a Set the timeline draws them from", () => {
    const patch = serverPatch({ missing: ["m1", "m2"] });
    assert.deepEqual([...patch.missingMedia], ["m1", "m2"]);
    assert.equal("missingMedia" in serverPatch({ head: "h" }), false, "absent: unchanged");
    assert.equal(initialState().missingMedia.size, 0);
    assert.equal(initialState().inactiveStyle, "both");
  });

  test("a selection of clips that no longer exist is dropped", () => {
    const state = { ...initialState(), selection: new Set(["gone", "c1"]) };
    const patch = serverPatch(
      { project: { tracks: [{ id: "t", clips: [{ id: "c1" }] }] }, head: "h" },
      state,
    );
    assert.deepEqual([...patch.selection], ["c1"]);
  });
});

describe("the placeholder selection (WP43)", () => {
  const answer = (placeholders) => ({
    project: { tracks: [], ...(placeholders ? { placeholders } : {}) },
    head: "h",
  });

  test("starts empty", () => {
    assert.equal(initialState().placeholderSelected, null);
  });

  test("a placeholder that no longer exists is dropped from the selection", () => {
    const state = { ...initialState(), placeholderSelected: "h1" };
    assert.equal(serverPatch(answer(undefined), state).placeholderSelected, null);
    assert.equal(serverPatch(answer([{ id: "h2" }]), state).placeholderSelected, null);
  });

  test("one that is still there stays", () => {
    const state = { ...initialState(), placeholderSelected: "h1" };
    assert.equal("placeholderSelected" in serverPatch(answer([{ id: "h1" }]), state), false);
  });
});

describe("live messages", () => {
  const state = { ...initialState(), head: "h1" };

  test("an anchor is handed on for the playhead clock, not applied here", () => {
    const anchor = { type: "anchor", position: 4800, playing: true, seq: 3 };
    const out = reduceLive(state, anchor);
    assert.deepEqual(out.anchor, anchor);
    assert.deepEqual(out.patch, {});
    assert.equal(out.refresh, false);
  });

  test("a clipboard preview's anchor is for the chip's meter, never the playhead", () => {
    const preview = { type: "preview", position: 480, playing: true, seq: 4, end: 9600 };
    const out = reduceLive(state, preview);
    assert.deepEqual(out.preview, preview);
    assert.equal(out.anchor, undefined);
    assert.deepEqual(out.patch, {});
  });

  test("the patch an accepted anchor makes: stopped lands the playhead, 1x again", () => {
    assert.deepEqual(anchorPatch({ position: 9, playing: false }), {
      playhead: 9,
      playing: false,
      speed: 1,
    });
    assert.deepEqual(anchorPatch({ position: 4800, playing: true, speed: 1.5 }), {
      playing: true,
    });
  });

  test("a changed head, from state_changed or hello, asks for a refresh", () => {
    assert.equal(reduceLive(state, { type: "state_changed", head: "h2" }).refresh, true);
    assert.equal(reduceLive(state, { type: "hello", head: "h2" }).refresh, true);
    assert.equal(reduceLive(state, { type: "state_changed", head: "h1" }).refresh, false);
    assert.equal(reduceLive(state, { type: "hello", head: "h1" }).refresh, false);
  });

  test("a notice is shown with the server's own text", () => {
    const out = reduceLive(state, { type: "notice", id: 3, text: "Device lost" });
    assert.deepEqual(out.notice, { id: 3, text: "Device lost" });
  });

  test("a meter frame is handed on for the status bar and changes no state", () => {
    const meter = { l: -12, r: -14, hold_l: -6, hold_r: -9 };
    const out = reduceLive(state, { type: "meter", meter });
    assert.deepEqual(out.meter, meter);
    assert.deepEqual(out.patch, {});
    assert.equal(out.refresh, false);
  });

  test("jobs and unknown messages change nothing", () => {
    assert.deepEqual(reduceLive(state, { type: "jobs", jobs: [] }).patch, {});
    assert.deepEqual(reduceLive(state, { type: "whatever" }).patch, {});
  });
});

describe("editing defaults", () => {
  test("range operations start on all tracks (reset on open) and the nudge step is 10 ms", () => {
    assert.equal(initialState().rangeMode, "all");
    assert.equal(initialState().trackSelection.size, 0);
    assert.equal(initialState().nudgeMs, 10);
  });
});

test("subscribers receive the previous state so heartbeats are not playback starts", async () => {
  const { resetState, setState, subscribe } = await import("../store.js");
  resetState();
  const transitions = [];
  const unsubscribe = subscribe((state, patch, previous) => {
    if ("playing" in patch) transitions.push([previous?.playing, state.playing]);
  });
  try {
    setState({ playing: true });
    setState({ followPaused: true });
    setState({ playing: true });
    setState({ playing: false });
    assert.deepEqual(transitions, [
      [false, true],
      [true, true],
      [true, false],
    ]);
  } finally {
    unsubscribe();
    resetState();
  }
});
