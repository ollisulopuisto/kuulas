// Every export honours the selection (owner, 2026-10-21): which time span and which tracks
// a selection means. Pure rules; app.js and the dialogs use them.
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  resolveExportSelection,
  selectionBody,
  selectionNotice,
  spanDots,
} from "../export-selection-model.js";

const RATE = 48000;
const s = (seconds) => seconds * RATE;
const clip = (id, from, to) => ({ id, start: s(from), length: s(to - from) });
const PROJECT = {
  rate: RATE,
  tracks: [
    { id: "a", name: "Anna", clips: [clip("a1", 10, 20), clip("a2", 30, 40)] },
    { id: "b", name: "Ville", clips: [clip("b1", 12, 18)] },
    { id: "c", name: "Music", clips: [clip("c1", 0, 60)] },
  ],
};
const LENGTH = s(60);
const base = { project: PROJECT, selection: new Set(), inPoint: null, outPoint: null };
const resolve = (patch) => resolveExportSelection({ ...base, ...patch }, { length: LENGTH });

describe("resolveExportSelection", () => {
  test("no selection: null (the whole mix, as before)", () => {
    assert.equal(resolve({}), null);
  });
  test("In/Out marks: that range, on all tracks by default", () => {
    assert.deepEqual(resolve({ inPoint: s(12), outPoint: s(18.5) }), {
      source: "marks",
      range: [s(12), s(18.5)],
      trackIds: null,
      names: [],
    });
  });
  test("marks with selected-tracks scope: those tracks, as Backspace/X use", () => {
    const got = resolve({
      inPoint: s(12),
      outPoint: s(18),
      rangeMode: "selected",
      trackSelection: new Set(["b", "a"]),
    });
    assert.deepEqual(got.trackIds, ["a", "b"]);
    assert.deepEqual(got.names, ["Anna", "Ville"]);
  });
  test("a mouse-painted range on lanes: those lanes", () => {
    const got = resolve({ inPoint: s(1), outPoint: s(2), rangeTracks: new Set(["c"]) });
    assert.deepEqual(got.trackIds, ["c"]);
  });
  test("marks beat selected clips", () => {
    const got = resolve({ inPoint: s(1), outPoint: s(2), selection: new Set(["a1"]) });
    assert.equal(got.source, "marks");
  });
  test("selected clips: their tracks over their combined span", () => {
    const got = resolve({ selection: new Set(["a1", "b1"]) });
    assert.deepEqual(got, {
      source: "clips",
      range: [s(10), s(20)],
      trackIds: ["a", "b"],
      names: ["Anna", "Ville"],
    });
  });
  test("clips on a track but far apart: one span from first start to last end", () => {
    const got = resolve({ selection: new Set(["a1", "a2"]) });
    assert.deepEqual(got.range, [s(10), s(40)]);
    assert.deepEqual(got.trackIds, ["a"]);
  });
  test("clips on every track: all tracks (null)", () => {
    const shorter = {
      ...PROJECT,
      tracks: PROJECT.tracks.map((t) => (t.id === "c" ? { ...t, clips: [clip("c1", 5, 55)] } : t)),
    };
    const got = resolve({ project: shorter, selection: new Set(["a1", "b1", "c1"]) });
    assert.equal(got.trackIds, null);
    assert.deepEqual(got.names, []);
  });
  test("a range that is the whole mix on all tracks is no selection", () => {
    assert.equal(
      resolve({ selection: new Set(["c1"]), project: { ...PROJECT, tracks: [PROJECT.tracks[2]] } }),
      null,
    );
  });
  test("selected clips that no longer exist: no selection", () => {
    assert.equal(resolve({ selection: new Set(["gone"]) }), null);
  });
  test("a muted track stays in the list; the export's mute rule silences it as today", () => {
    const muted = {
      ...PROJECT,
      tracks: PROJECT.tracks.map((t) => (t.id === "b" ? { ...t, mute: true } : t)),
    };
    const got = resolve({ project: muted, selection: new Set(["a1", "b1"]) });
    assert.deepEqual(got.trackIds, ["a", "b"]);
  });
  test("the span is cut at the mix length", () => {
    const got = resolve({ inPoint: s(50), outPoint: s(90) });
    assert.deepEqual(got.range, [s(50), s(60)]);
  });
});

describe("selectionBody", () => {
  test("range, and the tracks only when not all", () => {
    assert.deepEqual(selectionBody(resolve({ selection: new Set(["a1"]) })), {
      range: [s(10), s(20)],
      track_ids: ["a"],
    });
    assert.deepEqual(selectionBody(resolve({ inPoint: s(1), outPoint: s(2) })), {
      range: [s(1), s(2)],
    });
    assert.deepEqual(selectionBody(null), {});
  });
});

describe("spanDots and selectionNotice", () => {
  const t = (key, values) => `${key} ${JSON.stringify(values)}`;
  test("mm.ss-mm.ss like the automixer's preview names", () => {
    assert.equal(spanDots([s(12), s(18.5)], RATE), "00.12-00.18");
    assert.equal(spanDots([s(720), s(1110)], RATE), "12.00-18.30");
  });
  test("all tracks: says only the span", () => {
    const got = selectionNotice(resolve({ inPoint: s(720 / 60), outPoint: s(20) }), RATE, t);
    assert.ok(got.startsWith("ui.export.selection_only "));
    assert.ok(got.includes('"span":"00.12-00.20"'));
  });
  test("some tracks: names them too", () => {
    const got = selectionNotice(resolve({ selection: new Set(["a1", "b1"]) }), RATE, t);
    assert.ok(got.startsWith("ui.export.selection_only_tracks "));
    assert.ok(got.includes('"tracks":"Anna, Ville"'));
  });
  test("nothing selected: empty", () => {
    assert.equal(selectionNotice(null, RATE, t), "");
  });
});
