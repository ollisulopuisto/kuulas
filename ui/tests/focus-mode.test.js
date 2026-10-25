// Focus mode (WP28, docs/design/FOCUS-MODE.md section 7.3): the view-layer lane heights, the
// tween, the motion rule, the inactive lanes, walking and the solo round trip, as pure functions.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { registerAppCommands } from "../app-commands.js";
import { createRegistry } from "../commands.js";
import {
  FOCUS_SIDE_MAX,
  FOCUS_STRIP,
  focusHeights,
  focusResizeMs,
  followCurrent,
  inactiveTracks,
  outOfFocus,
  soloSteps,
  startFocus,
  stepFocusMode,
  stopFocus,
  tweenHeights,
} from "../focus-layout.js";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { BUS_HEIGHT, GROUP_GAP, layoutRows, MAX_LANE, MIN_LANE } from "../lanes.js";
import { CHECKED, MENU, menuTargets } from "../menu-model.js";

const track = (id, extra = {}) => ({ id, clips: [], ...extra });
const flat = {
  rate: 48_000,
  buses: [],
  tracks: [
    track("anna", { speaker: "Anna" }),
    track("ville", { speaker: "Ville" }),
    track("pekka", { speaker: "Pekka" }),
    track("theme", { kind: "music" }),
  ],
};
const sum = (heights) => Object.values(heights).reduce((a, b) => a + b, 0);

describe("focusHeights: the view-layer lane heights", () => {
  test("the focused lane takes most of the room, the others stay readable, the sum is the area", () => {
    const heights = focusHeights({ project: flat, focusIds: ["ville"], available: 400 });
    // The others share 40 % of the room: 53 px each, a waveform you can still read
    // (owner, 2026-10-23: "a BIT too extreme"; it was 16 px strips).
    assert.deepEqual(heights, { anna: 53, ville: 241, pekka: 53, theme: 53 });
    assert.equal(sum(heights), 400);
  });

  test("the others are never thinner than a strip, nor thicker than 64 px", () => {
    assert.equal(FOCUS_STRIP, 16);
    const one = { ...flat, tracks: flat.tracks.slice(0, 2) };
    const roomy = focusHeights({ project: one, focusIds: ["anna"], available: 1000 });
    assert.equal(roomy.ville, FOCUS_SIDE_MAX);
    const many = {
      rate: 48_000,
      tracks: Array.from({ length: 30 }, (_, i) => track(`t${i}`)),
    };
    const crowded = focusHeights({ project: many, focusIds: ["t0"], available: 600 });
    assert.equal(crowded.t1, FOCUS_STRIP);
  });

  test("an explicit strip height still wins", () => {
    const heights = focusHeights({ project: flat, focusIds: ["ville"], available: 400, strip: 16 });
    assert.deepEqual(heights, { anna: 16, ville: 352, pekka: 16, theme: 16 });
  });

  test("bus rows and group gaps keep their height and come off first", () => {
    const project = {
      rate: 48_000,
      buses: [{ id: "b1", name: "Voices" }],
      tracks: [track("a", { bus: "b1" }), track("b", { bus: "b1" }), track("m")],
    };
    const heights = focusHeights({ project, focusIds: ["a"], available: 300 });
    // A bus row (60) and one gap (14) are fixed; b and m share 40 % of what is left.
    const side = Math.floor((0.4 * (300 - BUS_HEIGHT - GROUP_GAP)) / 2);
    assert.equal(heights.a, 300 - BUS_HEIGHT - GROUP_GAP - 2 * side);
    assert.equal(heights.b, side);
    const layout = layoutRows(project, 80, { viewHeights: heights });
    assert.equal(layout.height, 300);
  });

  test("a speaker's split tracks share the room", () => {
    const project = { ...flat, tracks: [...flat.tracks, track("ville2", { speaker: "Ville" })] };
    const heights = focusHeights({ project, focusIds: ["ville", "ville2"], available: 301 });
    const side = Math.floor((0.4 * 301) / 3);
    assert.equal(heights.ville + heights.ville2, 301 - 3 * side);
    assert.ok(Math.abs(heights.ville - heights.ville2) <= 1);
  });

  test("the focused lane is clamped to the lane limits", () => {
    const tall = focusHeights({ project: flat, focusIds: ["anna"], available: 2000 });
    assert.equal(tall.anna, MAX_LANE);
    const tiny = focusHeights({ project: flat, focusIds: ["anna"], available: 40 });
    assert.equal(tiny.anna, MIN_LANE);
  });

  test("nothing to do: no project, no room, nothing focused, or the focus folded in a bus", () => {
    assert.equal(focusHeights({ project: null, focusIds: ["a"], available: 300 }), null);
    assert.equal(focusHeights({ project: flat, focusIds: ["anna"], available: 0 }), null);
    assert.equal(focusHeights({ project: flat, focusIds: [], available: 300 }), null);
    const project = {
      rate: 48_000,
      buses: [{ id: "b1", name: "Voices" }],
      tracks: [track("a", { bus: "b1" }), track("b", { bus: "b1" }), track("m")],
    };
    const collapsed = new Set(["b1"]);
    assert.equal(focusHeights({ project, focusIds: ["a"], available: 300, collapsed }), null);
  });
});

describe("layoutRows with view heights", () => {
  test("a view height wins over the own height and is not clamped up to the lane minimum", () => {
    const layout = layoutRows(flat, 80, {
      laneHeights: { anna: 120 },
      viewHeights: { anna: 16, ville: 200 },
    });
    const by = Object.fromEntries(layout.rows.map((row) => [row.id, row.height]));
    assert.deepEqual(by, { anna: 16, ville: 200, pekka: 80, theme: 80 });
  });
  test("a non-finite view height is ignored", () => {
    const layout = layoutRows(flat, 80, { viewHeights: { anna: Number.NaN } });
    assert.equal(layout.rows[0].height, 80);
  });
});

describe("tweenHeights", () => {
  const from = { a: 100, b: 100 };
  const to = { a: 184, b: 16 };
  test("starts at from, ends exactly at to", () => {
    assert.deepEqual(tweenHeights(from, to, 0), from);
    assert.deepEqual(tweenHeights(from, to, 1), to);
    assert.deepEqual(tweenHeights(from, to, 5), to);
  });
  test("eases out: more than half way at the midpoint, whole pixels", () => {
    const mid = tweenHeights(from, to, 0.5);
    assert.ok(mid.a > 142 && mid.a < 184, String(mid.a));
    assert.ok(mid.b < 58 && mid.b > 16, String(mid.b));
    assert.ok(Number.isInteger(mid.a) && Number.isInteger(mid.b));
  });
  test("a lane missing from `from` starts at its target", () => {
    assert.deepEqual(tweenHeights({}, { c: 50 }, 0.3), { c: 50 });
  });
});

describe("focusResizeMs: the motion rule (GUI-DESIGN section 20)", () => {
  test("120 ms at full, shorter at subtle, instant when off or while playing", () => {
    assert.equal(focusResizeMs("full"), 120);
    const subtle = focusResizeMs("subtle");
    assert.ok(subtle > 0 && subtle < 120);
    assert.equal(focusResizeMs("off"), 0);
    assert.equal(focusResizeMs("full", { playing: true }), 0);
  });
});

describe("outOfFocus: the lanes drawn inactive", () => {
  test("every track not in focus; none without focus", () => {
    assert.deepEqual([...outOfFocus(flat, ["ville"])], ["anna", "pekka", "theme"]);
    assert.equal(outOfFocus(flat, null).size, 0);
    assert.equal(outOfFocus(flat, []).size, 0);
  });
});

describe("inactiveTracks: the range scope's inactive lanes plus focus mode's", () => {
  test("focus alone, scope alone, both together", () => {
    const base = { project: flat, rangeMode: "all", trackSelection: new Set() };
    assert.deepEqual([...inactiveTracks({ ...base, focusMode: { ids: ["anna"] } })].sort(), [
      "pekka",
      "theme",
      "ville",
    ]);
    assert.equal(inactiveTracks(base).size, 0);
    const scoped = { ...base, rangeMode: "selected", trackSelection: new Set(["anna", "ville"]) };
    assert.deepEqual([...inactiveTracks(scoped)].sort(), ["pekka", "theme"]);
    const both = { ...scoped, focusMode: { ids: ["pekka"] } };
    assert.deepEqual([...inactiveTracks(both)].sort(), ["anna", "pekka", "theme", "ville"]);
  });
});

describe("entering, walking and leaving", () => {
  const tracks = [
    { id: "a1", speaker: "Anna" },
    { id: "v", speaker: "Ville" },
    { id: "a2", speaker: "Anna" },
    { id: "m", solo: true },
  ];
  test("start focuses the current track's speaker; no current track, no focus", () => {
    assert.deepEqual(startFocus(tracks, "a2"), { ids: ["a1", "a2"], soloBefore: null });
    assert.equal(startFocus(tracks, null), null);
    assert.equal(startFocus(tracks, "nope"), null);
  });
  test("with solo, the solo set as it was is remembered", () => {
    assert.deepEqual(startFocus(tracks, "v", { solo: true }), { ids: ["v"], soloBefore: ["m"] });
    const quiet = tracks.map((item) => ({ ...item, solo: false }));
    assert.deepEqual(startFocus(quiet, "v", { solo: true }).soloBefore, []);
  });
  test("stop hands back the solo set to restore, or null when focus did not solo", () => {
    assert.deepEqual(stopFocus({ ids: ["v"], soloBefore: ["m"] }), { restoreSolo: ["m"] });
    assert.deepEqual(stopFocus({ ids: ["v"], soloBefore: null }), { restoreSolo: null });
    assert.deepEqual(stopFocus(null), { restoreSolo: null });
  });
  test("up and down walk the focus by speaker and keep the remembered solo set", () => {
    const mode = { ids: ["v"], soloBefore: ["m"] };
    assert.deepEqual(stepFocusMode(tracks, mode, 1), { ids: ["a1", "a2"], soloBefore: ["m"] });
    assert.deepEqual(stepFocusMode(tracks, mode, -1), { ids: ["a1", "a2"], soloBefore: ["m"] });
    const last = { ids: ["m"], soloBefore: null };
    assert.equal(stepFocusMode(tracks, last, 1), last);
  });
  test("a click that makes another track current moves the focus there", () => {
    assert.deepEqual(followCurrent(tracks, ["v"], "a1"), ["a1", "a2"]);
    assert.deepEqual(followCurrent(tracks, ["a1", "a2"], "a2"), ["a1", "a2"]);
    assert.deepEqual(followCurrent(tracks, ["v"], null), ["v"]);
  });
});

describe("soloSteps: the additive solo toggles that reach a solo set", () => {
  const tracks = [
    { id: "a", solo: true },
    { id: "b", solo: false },
    { id: "c", solo: true },
  ];
  test("toggles exactly the tracks whose solo differs, in track order", () => {
    assert.deepEqual(soloSteps(tracks, ["b", "c"]), ["a", "b"]);
    assert.deepEqual(soloSteps(tracks, []), ["a", "c"]);
    assert.deepEqual(soloSteps(tracks, ["a", "c"]), []);
  });
  test("a track that no longer exists is skipped", () => {
    assert.deepEqual(soloSteps(tracks, ["a", "c", "gone"]), []);
  });
});

describe("the focus commands in the registry", () => {
  const tracks = [
    { id: "a", speaker: "Anna" },
    { id: "v", speaker: "Ville" },
  ];
  function setup(state) {
    const calls = [];
    const registry = createRegistry();
    const actions = new Proxy(
      {},
      {
        get:
          (_, name) =>
          (...args) =>
            calls.push([name, ...args]),
      },
    );
    const app = {
      getState: () => state,
      patch: (patch) => calls.push(["patch", patch]),
      seek: () => {},
      totalFrames: () => 0,
    };
    registerAppCommands(registry, { actions, app });
    return { registry, calls };
  }
  test("the four commands are ready and need a project", () => {
    const { registry } = setup({});
    for (const id of ["view.focus", "view.focus_solo"]) {
      assert.equal(registry.status(id), "ready", id);
      assert.equal(registry.can(id, {}), false, id);
      assert.equal(registry.can(id, { project: { tracks } }), true, id);
    }
    for (const id of ["view.focus_shrink", "view.focus_hide_others"])
      assert.equal(registry.status(id), "ready", id);
  });
  test("F-keys ask the app to toggle focus, with or without solo", () => {
    const { registry, calls } = setup({ project: { tracks }, focusTrack: "a" });
    registry.run("view.focus", null, { project: { tracks } });
    registry.run("view.focus_solo", null, { project: { tracks } });
    assert.deepEqual(calls, [
      ["toggleFocus", { solo: false }],
      ["toggleFocus", { solo: true }],
    ]);
  });
  test("Down in focus mode walks the focus to the next speaker and makes it current", () => {
    const focusMode = { ids: ["a"], soloBefore: null };
    const state = { project: { tracks }, focusTrack: "a", focusMode };
    const { registry, calls } = setup(state);
    registry.run("track.next", null, state);
    assert.deepEqual(calls, [["setFocus", { ids: ["v"], soloBefore: null }, "v"]]);
  });
  test("without focus mode Down only moves the current track", () => {
    const state = { project: { tracks }, focusTrack: "a" };
    const { registry, calls } = setup(state);
    registry.run("track.next", null, state);
    assert.equal(calls[0][0], "patch");
    assert.equal(calls[0][1].focusTrack, "v");
  });
});

describe("the focus commands: keys, menu, switches", () => {
  const keysOf = (id) => DEFAULT_KEYMAP.find((entry) => entry.id === id)?.keys;
  test("Shift+F focuses, Alt+Shift+F focuses and solos, Alt+F hides other speakers' words", () => {
    // F stays Fit selection (owner, 2026-10-18); nothing needs AltGr or Shift+digit.
    assert.deepEqual(keysOf("view.focus"), { mac: "Shift+F", other: "Shift+F" });
    assert.deepEqual(keysOf("view.focus_solo"), { mac: "Alt+Shift+F", other: "Alt+Shift+F" });
    assert.deepEqual(keysOf("view.focus_hide_others"), { mac: "Alt+F", other: "Alt+F" });
    assert.deepEqual(keysOf("view.focus_shrink"), { mac: null, other: null });
    assert.deepEqual(keysOf("view.fit_selection"), { mac: "F", other: "F" });
  });
  test("all four are in the View menu, and the switches show their state", () => {
    const view = MENU.find((top) => top.id === "view");
    const targets = menuTargets([view]);
    const ids = ["view.focus", "view.focus_solo", "view.focus_shrink", "view.focus_hide_others"];
    for (const id of ids) assert.ok(targets.includes(id), id);
    assert.equal(CHECKED["view.focus"]({ focusMode: { ids: ["a"] } }), true);
    assert.equal(CHECKED["view.focus"]({ focusMode: null }), false);
    assert.equal(CHECKED["view.focus_shrink"]({}), true);
    assert.equal(CHECKED["view.focus_shrink"]({ focusShrink: false }), false);
    assert.equal(CHECKED["view.focus_hide_others"]({}), false);
    assert.equal(CHECKED["view.focus_hide_others"]({ focusHideOthers: true }), true);
  });
});
