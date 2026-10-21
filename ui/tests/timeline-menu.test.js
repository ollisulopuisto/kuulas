import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { DEFAULT_KEYMAP } from "../keymap-default.js";
import { MENU, menuTargets } from "../menu-model.js";
import {
  contextPress,
  menuFromSections,
  timelineMenuIds,
  timelineMenuItems,
  timelineTarget,
} from "../timeline-menu.js";

const project = {
  tracks: [
    {
      id: "t1",
      clips: [{ id: "c1" }, { id: "c2", group: "g" }, { id: "c3", group: "g" }],
    },
    { id: "t2", clips: [] },
  ],
};
const base = { project, selection: new Set(), inPoint: null, outPoint: null, playhead: 0 };
const flat = (sections) => sections.flatMap((s) => s.items.map((i) => i.id));
const all = () => true;
const none = () => false;
const trackRow = (id) => ({ kind: "track", id });

describe("which target a pointer hit is", () => {
  test("the ruler", () => {
    assert.equal(timelineTarget({ area: "ruler", frame: 5 }, base).kind, "ruler");
  });
  test("a clip", () => {
    const hit = { area: "lane", frame: 5, clip: { id: "c1" }, row: trackRow("t1") };
    assert.equal(timelineTarget(hit, base).kind, "clip");
  });
  test("empty lane space", () => {
    const hit = { area: "lane", frame: 5, clip: null, row: trackRow("t2") };
    assert.equal(timelineTarget(hit, base).kind, "lane");
  });
  test("inside the marked range is the range, even over a clip", () => {
    const state = { ...base, inPoint: 10, outPoint: 20 };
    const hit = { area: "lane", frame: 15, clip: { id: "c1" }, row: trackRow("t1") };
    assert.equal(timelineTarget(hit, state).kind, "range");
    assert.equal(timelineTarget({ ...hit, frame: 25, clip: null }, state).kind, "lane");
  });
  test("a lone mark is no range", () => {
    const state = { ...base, inPoint: 10, outPoint: null };
    const hit = { area: "lane", frame: 15, clip: null, row: trackRow("t1") };
    assert.equal(timelineTarget(hit, state).kind, "lane");
  });
  test("the ruler wins over the range band", () => {
    const state = { ...base, inPoint: 10, outPoint: 20 };
    assert.equal(timelineTarget({ area: "ruler", frame: 15 }, state).kind, "ruler");
  });
});

describe("the sections per target", () => {
  const has = (kind, wanted) => {
    const ids = flat(timelineMenuItems(base, { kind }, all));
    for (const id of wanted) assert.ok(ids.includes(id), `${kind}: ${id}`);
  };
  test("clip: Locate / Relink media is always there, missing or not (owner, 2026-10-21)", () => {
    has("clip", ["clip.relink_media"]);
    const sections = timelineMenuItems(base, { kind: "clip" }, all);
    assert.ok(sections.some((s) => s.titleKey === "ui.ctx.media"));
  });
  test("clip: clipboard, paste forms, edit, select, adjust", () => {
    has("clip", [
      "edit.cut",
      "edit.copy",
      "edit.paste",
      "edit.paste_insert",
      "edit.paste_track",
      "edit.paste_same",
      "edit.delete",
      "edit.split",
      "edit.group",
      "edit.ungroup",
      "edit.merge",
      "clip.mute",
      "clip.fade",
      "select.forward_from_clips",
      "select.forward_all_tracks_from_clips",
      "select.none",
      "select.invert",
      "edit.trim_start",
      "edit.nudge_left",
      "clip.gain_up",
      "clip.pan_left",
    ]);
  });
  test("range: cut, copy, delete, close gap, loop, play, select clips, clear, export", () => {
    has("range", [
      "edit.cut",
      "edit.copy",
      "edit.delete",
      "edit.close_gap_all",
      "transport.loop",
      "transport.play_selection",
      "select.clips_in_range",
      "mark.clear",
      "export.regions",
    ]);
  });
  test("lane: paste forms, marker, placeholder, in/out, select forward", () => {
    has("lane", [
      "edit.paste",
      "edit.paste_insert",
      "edit.paste_track",
      "edit.paste_same",
      "marker.add",
      "placeholder.add",
      "mark.in",
      "mark.out",
      "select.forward",
    ]);
  });
  test("ruler: marker, in/out, zoom", () => {
    has("ruler", ["marker.add", "mark.in", "mark.out", "view.zoom_in", "view.zoom_out"]);
  });
  test("an id appears once per menu", () => {
    for (const kind of ["clip", "range", "lane", "ruler"]) {
      const ids = flat(timelineMenuItems(base, { kind }, all));
      assert.equal(new Set(ids).size, ids.length, kind);
    }
  });
  test("only what is possible is listed: can(id, state) decides and gets the state", () => {
    const seen = [];
    const sections = timelineMenuItems(base, { kind: "lane" }, (id, state) => {
      seen.push(state);
      return id === "marker.add";
    });
    assert.deepEqual(
      sections.flatMap((s) => s.items).map((i) => i.id),
      ["marker.add"],
    );
    assert.ok(sections.flatMap((s) => s.items).every((i) => i.enabled));
    assert.ok(seen.every((s) => s === base));
  });
  test("a section with nothing possible is left out, and so is a menu with nothing possible", () => {
    const only = timelineMenuItems(base, { kind: "lane" }, (id) => id === "marker.add");
    assert.equal(only.length, 1);
    assert.deepEqual(timelineMenuItems(base, { kind: "clip" }, none), []);
  });
  test("items keep their order within a section", () => {
    const can = (id) => id === "edit.paste_same" || id === "edit.paste_track";
    const paste = timelineMenuItems(base, { kind: "lane" }, can)[0];
    assert.deepEqual(
      paste.items.map((i) => i.id),
      ["edit.paste_track", "edit.paste_same"],
    );
  });
  test("every section has a title key", () => {
    for (const kind of ["clip", "range", "lane", "ruler"])
      for (const s of timelineMenuItems(base, { kind }, all))
        assert.match(s.titleKey, /^ui\.ctx\./);
  });
});

describe("flattening for the menu", () => {
  const resolved = new Map([
    ["marker.add", { label: "Add marker", keys: "M", tooltip: "Put one · M" }],
  ]);
  test("a caption before each section, items carry label, keys and tooltip", () => {
    const sections = [{ titleKey: "ui.ctx.insert", items: [{ id: "marker.add", enabled: true }] }];
    const items = menuFromSections(sections, resolved, (key) => `T:${key}`);
    assert.deepEqual(items[0], { separator: true, caption: "T:ui.ctx.insert" });
    assert.equal(items[1].id, "marker.add");
    assert.equal(items[1].label, "Add marker");
    assert.equal(items[1].keys, "M");
    assert.equal(items[1].tooltip, "Put one · M");
    assert.equal(items[1].enabled, true);
  });
  test("a rule between sections, not before the first", () => {
    const sections = [
      { titleKey: "a", items: [{ id: "marker.add", enabled: true }] },
      { titleKey: "b", items: [{ id: "marker.add", enabled: false }] },
    ];
    const items = menuFromSections(sections, resolved, (k) => k);
    assert.deepEqual(
      items.map((i) => (i.separator ? (i.caption ?? "-") : i.id)),
      ["a", "marker.add", "-", "b", "marker.add"],
    );
    assert.equal(items[4].enabled, false);
  });
});

describe("what a right press changes", () => {
  const hitClip = (id) => ({ area: "lane", frame: 100, clip: { id }, row: trackRow("t1") });
  test("an unselected clip becomes the selection, with its group", () => {
    const plan = contextPress(hitClip("c2"), { ...base, selection: new Set(["c1"]) });
    assert.deepEqual([...plan.selection].sort(), ["c2", "c3"]);
    assert.equal(plan.seek, null);
  });
  test("a selected clip leaves the selection alone", () => {
    const plan = contextPress(hitClip("c1"), { ...base, selection: new Set(["c1", "c3"]) });
    assert.equal(plan.selection, undefined);
  });
  test("inside the range: nothing changes", () => {
    const state = { ...base, inPoint: 50, outPoint: 150 };
    assert.deepEqual(contextPress(hitClip("c1"), state), { kind: "range", seek: null });
  });
  test("empty lane: the playhead goes there and the track is focused", () => {
    const hit = { area: "lane", frame: 77, clip: null, row: trackRow("t2") };
    const plan = contextPress(hit, base);
    assert.equal(plan.seek, 77);
    assert.equal(plan.focusTrack, "t2");
  });
  test("ruler: the playhead goes there", () => {
    assert.equal(contextPress({ area: "ruler", frame: 9 }, base).seek, 9);
  });
});

describe("the menus only name commands that exist", () => {
  // The keymap data carries each command's label key; the menu bar names the rest.
  test("each id is a command of the keymap or the menu bar", () => {
    const known = new Set([...DEFAULT_KEYMAP.map((e) => e.id), ...menuTargets(MENU)]);
    for (const id of timelineMenuIds()) assert.ok(known.has(id), id);
  });
});
