import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  collectDroppedFiles,
  createDropMemory,
  dropGhosts,
  dropLabel,
  importOptionsFor,
  isAudioName,
  pickerPlacement,
  resolveDropTarget,
} from "../import-drop.js";
import { layoutRows, RULER_HEIGHT } from "../lanes.js";

const project = {
  tracks: [
    { id: "t1", clips: [] },
    { id: "t2", clips: [] },
  ],
  buses: [],
};
const layout = layoutRows(project, 80);
const view = { scroll: 0, zoom: 100, scrollY: 0, width: 1000, height: 600 };
const at = (x, y, alt = false) =>
  resolveDropTarget({ x, y, alt }, { layout, project, view, count: 3 });

describe("drop target", () => {
  test("below the tracks: new tracks at the start, in sync", () => {
    const target = at(400, RULER_HEIGHT + 400);
    assert.deepEqual(target, {
      kind: "new",
      startFrame: 0,
      trackId: null,
      mode: "side_by_side",
      count: 3,
    });
  });

  test("alt below the tracks: one after another", () => {
    assert.equal(at(400, RULER_HEIGHT + 400, true).mode, "sequential");
  });

  test("on the ruler: new tracks starting at that time", () => {
    const target = at(250, 10);
    assert.equal(target.kind, "ruler");
    assert.equal(target.startFrame, 25_000);
    assert.equal(target.trackId, null);
    assert.equal(target.mode, "side_by_side");
  });

  test("on a lane: start at the drop time, remembering the lane", () => {
    const target = at(250, RULER_HEIGHT + 100);
    assert.equal(target.kind, "lane");
    assert.equal(target.trackId, "t2");
    assert.equal(target.startFrame, 25_000);
  });

  test("the lane area scrolled: the row under the pointer counts", () => {
    const scrolled = { ...view, scrollY: 80 };
    const target = resolveDropTarget(
      { x: 0, y: RULER_HEIGHT + 10 },
      { layout, project, view: scrolled, count: 1 },
    );
    assert.equal(target.trackId, "t2");
  });

  test("left of time zero never starts before zero", () => {
    const scrolled = { ...view, scroll: 0 };
    assert.equal(at(-30, 10).startFrame, 0);
    assert.equal(
      resolveDropTarget({ x: -30, y: 10 }, { layout, project, view: scrolled }).startFrame,
      0,
    );
  });

  test("outside the timeline (negative y): the default, new tracks at the start", () => {
    assert.equal(at(100, -5).kind, "new");
  });

  test("an empty project: any point is new tracks at the start", () => {
    const empty = layoutRows({ tracks: [], buses: [] }, 80);
    const target = resolveDropTarget(
      { x: 300, y: RULER_HEIGHT + 20 },
      { layout: empty, project: { tracks: [], buses: [] }, view, count: 2 },
    );
    assert.equal(target.kind, "new");
    assert.equal(target.startFrame, 0);
  });
});

describe("what the import sends", () => {
  const prefs = { order: "given", trackNaming: "file" };
  test("the default drop sends the plain defaults", () => {
    const target = at(400, RULER_HEIGHT + 400);
    assert.deepEqual(importOptionsFor(target, prefs), {
      mode: "side_by_side",
      order: "given",
      track_naming: "file",
      start_frame: 0,
    });
  });

  test("a lane drop sends its time and its track, and the remembered choices", () => {
    const target = at(250, RULER_HEIGHT + 100);
    const options = importOptionsFor(target, { order: "name", trackNaming: "person" });
    assert.equal(options.mode, "sequential"); // one file after another on that track
    assert.equal(options.order, "name");
    assert.equal(options.track_naming, "person");
    assert.equal(options.start_frame, 25_000);
    assert.equal(typeof options.onto_track, "string");
  });

  test("no target (the picker) is new tracks at the start", () => {
    assert.equal(importOptionsFor(null, prefs).start_frame, 0);
    assert.equal(importOptionsFor(null, prefs).mode, "side_by_side");
  });
});

describe("drop preview", () => {
  const preview = (over) => ({
    kind: "new",
    startFrame: 0,
    trackId: null,
    mode: "side_by_side",
    count: 3,
    ...over,
  });
  const size = { width: 1000, height: 600 };

  test("new tracks: an insertion line under the last track and one ghost per file", () => {
    const g = dropGhosts(preview(), { layout, view, size });
    assert.equal(g.line.orientation, "horizontal");
    assert.equal(g.line.y, RULER_HEIGHT + layout.height + 2);
    assert.equal(g.ghosts.length, 3);
    assert.ok(g.ghosts[0].y > g.line.y);
    assert.ok(g.ghosts[1].y > g.ghosts[0].y);
    assert.equal(g.ghosts[0].x, 0);
  });

  test("one after another: ghosts end to end on one row", () => {
    const g = dropGhosts(preview({ mode: "sequential" }), { layout, view, size });
    assert.equal(g.ghosts.length, 3);
    assert.equal(new Set(g.ghosts.map((x) => x.y)).size, 1);
    assert.ok(g.ghosts[1].x >= g.ghosts[0].x + g.ghosts[0].w);
  });

  test("a time drop: a vertical line at the start and ghosts from there", () => {
    const g = dropGhosts(preview({ kind: "lane", startFrame: 25_000, trackId: "t1" }), {
      layout,
      view,
      size,
    });
    assert.deepEqual(g.line, { orientation: "vertical", x: 250 });
    assert.equal(g.ghosts[0].x, 250);
  });

  test("a hundred files draw a handful of ghosts, not a hundred", () => {
    const g = dropGhosts(preview({ count: 100 }), { layout, view, size });
    assert.ok(g.ghosts.length <= 8);
  });

  test("ghosts stay on the canvas when the lanes fill it", () => {
    const tall = layoutRows(
      { tracks: Array.from({ length: 12 }, (_, i) => ({ id: `t${i}` })), buses: [] },
      80,
    );
    const g = dropGhosts(preview(), { layout: tall, view, size });
    for (const ghost of g.ghosts) assert.ok(ghost.y + ghost.h <= size.height);
  });

  test("the label says what will happen", () => {
    assert.deepEqual(dropLabel(preview()), { key: "ui.import.drop_new", params: { count: 3 } });
    assert.deepEqual(dropLabel(preview({ mode: "sequential" })), {
      key: "ui.import.drop_sequence",
      params: { count: 3 },
    });
    const timed = dropLabel(preview({ kind: "ruler", startFrame: 48_000 }));
    assert.equal(timed.key, "ui.import.drop_at");
    assert.equal(timed.params.count, 3);
    assert.equal(typeof timed.params.time, "string");
  });
});

describe("audio names", () => {
  test("audio and video files pass, other files and dot-files do not", () => {
    assert.equal(isAudioName("take1.WAV"), true);
    assert.equal(isAudioName("Zoom.m4a"), true);
    assert.equal(isAudioName("clip.mp4"), true);
    assert.equal(isAudioName("notes.txt"), false);
    assert.equal(isAudioName("._take1.wav"), false);
    assert.equal(isAudioName(".DS_Store"), false);
    assert.equal(isAudioName("wav"), false);
  });
});

// Fake FileSystemEntry trees, shaped like the browser's.
const file = (name) => ({ isFile: true, isDirectory: false, name, file: (ok) => ok({ name }) });
const dir = (name, children, batch = 2) => ({
  isFile: false,
  isDirectory: true,
  name,
  createReader() {
    let at = 0;
    return {
      readEntries(ok) {
        const slice = children.slice(at, at + batch);
        at += batch;
        ok(slice);
      },
    };
  },
});

describe("dropped folders", () => {
  test("a folder gives its audio files, in name order, past the reader's batches", async () => {
    const folder = dir("Zoom", [
      file("b.wav"),
      file("notes.txt"),
      file("a.wav"),
      file(".DS_Store"),
      file("c10.wav"),
      file("c2.wav"),
    ]);
    const files = await collectDroppedFiles([folder], []);
    assert.deepEqual(
      files.map((f) => f.name),
      ["a.wav", "b.wav", "c2.wav", "c10.wav"],
    );
  });

  test("subfolders are walked", async () => {
    const folder = dir("Rec", [dir("Tr", [file("x.flac")]), file("y.wav")]);
    const files = await collectDroppedFiles([folder], []);
    assert.deepEqual(files.map((f) => f.name).sort(), ["x.flac", "y.wav"]);
  });

  test("loose files are kept as dropped, even with an odd extension", async () => {
    const files = await collectDroppedFiles([file("voice.dat")], []);
    assert.deepEqual(
      files.map((f) => f.name),
      ["voice.dat"],
    );
  });

  test("without entries (an old browser) the plain file list is used", async () => {
    const plain = [{ name: "p.wav" }];
    assert.equal(await collectDroppedFiles([], plain), plain);
  });

  test("an unreadable folder costs that folder, not the drop", async () => {
    const broken = {
      isFile: false,
      isDirectory: true,
      name: "bad",
      createReader: () => ({ readEntries: (_ok, fail) => fail(new Error("denied")) }),
    };
    const files = await collectDroppedFiles([broken, file("ok.wav")], []);
    assert.deepEqual(
      files.map((f) => f.name),
      ["ok.wav"],
    );
  });
});

describe("the picker imports onto the selected track (owner, 2026-10-19)", () => {
  const project = {
    tracks: [
      { id: "a", clips: [{ id: "c1", start: 0, length: 1000 }] },
      { id: "e", clips: [] },
    ],
  };
  test("an empty selected track: the files start at the play cursor", () => {
    assert.deepEqual(pickerPlacement(project, "e", 480), { onto_track: "e", start_frame: 480 });
  });
  test("a track with material: after its last clip when the cursor is inside it", () => {
    assert.deepEqual(pickerPlacement(project, "a", 400), { onto_track: "a", start_frame: 1000 });
  });
  test("a track with material: at the cursor when it is past the last clip", () => {
    assert.deepEqual(pickerPlacement(project, "a", 5000), { onto_track: "a", start_frame: 5000 });
  });
  test("no selected track, or one that is gone: null (new tracks, as before)", () => {
    assert.equal(pickerPlacement(project, null, 0), null);
    assert.equal(pickerPlacement(project, "nope", 0), null);
    assert.equal(pickerPlacement(null, "a", 0), null);
  });
});

describe("a drop on a lane goes onto that track (owner, 2026-10-19)", () => {
  test("the options carry the track, one after another from the drop time", () => {
    const options = importOptionsFor(
      { kind: "lane", trackId: "t1", startFrame: 4800, mode: "side_by_side" },
      { order: "given", trackNaming: "file" },
    );
    assert.equal(options.onto_track, "t1");
    assert.equal(options.mode, "sequential");
    assert.equal(options.start_frame, 4800);
  });
  test("a drop in the ruler or in empty space still makes new tracks", () => {
    for (const kind of ["new", "ruler"]) {
      const options = importOptionsFor(
        { kind, trackId: null, startFrame: 0, mode: "side_by_side" },
        { order: "given", trackNaming: "file" },
      );
      assert.equal(options.onto_track, undefined);
    }
  });
});

describe("the drop place survives until the desktop window's paths arrive (owner, 2026-10-19)", () => {
  const where = { kind: "lane", trackId: "t1", startFrame: 4800, mode: "side_by_side" };
  test("a drop target remembered for a moment is given back once", () => {
    const memory = createDropMemory();
    memory.remember(where, 1000);
    assert.deepEqual(memory.take(1500), where);
    assert.equal(memory.take(1600), null);
  });
  test("a target that is too old is not used (a picker import much later)", () => {
    const memory = createDropMemory({ maxAgeMs: 3000 });
    memory.remember(where, 1000);
    assert.equal(memory.take(4001), null);
  });
  test("a newer drop replaces an older one, and nothing remembered gives null", () => {
    const memory = createDropMemory();
    assert.equal(memory.take(10), null);
    memory.remember(where, 100);
    memory.remember({ ...where, startFrame: 9600 }, 200);
    assert.equal(memory.take(300).startFrame, 9600);
  });
  test("time going backwards counts as just now", () => {
    const memory = createDropMemory();
    memory.remember(where, 5000);
    assert.deepEqual(memory.take(4000), where);
  });
});
