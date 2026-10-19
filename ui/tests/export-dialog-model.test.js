// The "(options)…" export dialog: which formats it lists, what it starts from, and what it asks
// the export for. Pure rules; the DOM is export-dialog.js.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  bitrateChoices,
  defaultBitrate,
  depthChoices,
  dialogFormats,
  exportBody,
  hasRange,
  LUFS_PRESETS,
  lufsPresetOf,
  mergeMemory,
  pickBitrate,
  pickDepth,
  pickFormat,
  quickPlan,
  silentTracks,
  sizeEstimate,
  startOptions,
  validateOptions,
} from "../export-dialog-model.js";

const ALL = [
  { id: "wav", label: "WAV" },
  { id: "flac", label: "FLAC" },
  { id: "mp3", label: "MP3" },
];

describe("dialogFormats", () => {
  test("lists the server's formats in its order", () => {
    assert.deepEqual(
      dialogFormats(ALL).map((f) => f.id),
      ["wav", "flac", "mp3"],
    );
  });
  test("before the server has answered, WAV and FLAC (no codec needed)", () => {
    assert.deepEqual(
      dialogFormats(null).map((f) => f.id),
      ["wav", "flac"],
    );
  });
});

describe("pickFormat", () => {
  test("the remembered format when it is offered, else the first", () => {
    assert.equal(pickFormat(ALL, "mp3"), "mp3");
    assert.equal(pickFormat(ALL, "ogg"), "wav");
    assert.equal(pickFormat(ALL, undefined), "wav");
    assert.equal(pickFormat([], "mp3"), "wav");
  });
});

const TRACKS = [
  { id: "a", name: "Olli", mute: false, solo: false, bus: null },
  { id: "b", name: "Maija", mute: true, solo: false, bus: null },
  { id: "c", name: "Ville", mute: false, solo: false, bus: "x" },
];
const PROJECT = { rate: 48000, tracks: TRACKS, buses: [{ id: "x", mute: false }] };
const MARKS = { inPoint: 48000, outPoint: 144000 };
const NO_MARKS = { inPoint: null, outPoint: null };

describe("hasRange", () => {
  test("needs an in mark before an out mark", () => {
    assert.equal(hasRange(MARKS), true);
    assert.equal(hasRange(NO_MARKS), false);
    assert.equal(hasRange({ inPoint: 5, outPoint: null }), false);
    assert.equal(hasRange({ inPoint: 9, outPoint: 9 }), false);
  });
});

describe("silentTracks (the mixer's rule)", () => {
  test("muted tracks are silent", () => {
    assert.deepEqual(
      silentTracks(PROJECT).map((x) => x.name),
      ["Maija"],
    );
  });
  test("while anything is soloed only the soloed tracks sound", () => {
    const soloed = { ...PROJECT, tracks: TRACKS.map((x) => ({ ...x, solo: x.id === "b" })) };
    assert.deepEqual(
      silentTracks(soloed).map((x) => x.name),
      ["Olli", "Ville"],
    );
  });
  test("a muted bus silences its tracks", () => {
    const muted = { ...PROJECT, buses: [{ id: "x", mute: true }] };
    assert.deepEqual(
      silentTracks(muted).map((x) => x.name),
      ["Maija", "Ville"],
    );
  });
  test("no project, nothing silent", () => {
    assert.deepEqual(silentTracks(null), []);
  });
});

describe("loudness presets", () => {
  test("off, podcast, streaming, broadcast", () => {
    assert.deepEqual(
      LUFS_PRESETS.map((p) => [p.id, p.lufs]),
      [
        ["off", null],
        ["podcast", -16],
        ["streaming", -14],
        ["broadcast", -23],
      ],
    );
  });
  test("a target finds its preset, else custom", () => {
    assert.equal(lufsPresetOf(null), "off");
    assert.equal(lufsPresetOf(-16), "podcast");
    assert.equal(lufsPresetOf(-18), "custom");
  });
});

describe("bit depth and bitrate by format", () => {
  test("PCM formats have depths, lossy ones do not", () => {
    assert.deepEqual(depthChoices("wav"), [16, 24, 32]);
    assert.deepEqual(depthChoices("flac"), [16, 24]);
    assert.deepEqual(depthChoices("mp3"), []);
  });
  test("the remembered depth when the format has it, else 24", () => {
    assert.equal(pickDepth("flac", 32), 24);
    assert.equal(pickDepth("wav", 16), 16);
    assert.equal(pickDepth("wav", undefined), 24);
  });
  test("MP3 offers 128 to 320, the other lossy formats their own", () => {
    assert.deepEqual(bitrateChoices("mp3"), [128, 160, 192, 256, 320]);
    assert.deepEqual(bitrateChoices("wav"), []);
    assert.ok(bitrateChoices("opus").includes(64));
  });
  test("the default follows the channels like the server", () => {
    assert.equal(defaultBitrate("mp3", 1), 128);
    assert.equal(defaultBitrate("mp3", 2), 192);
    assert.equal(defaultBitrate("wav", 2), null);
  });
  test("a remembered bitrate only when this format offers it", () => {
    assert.equal(pickBitrate("mp3", 256), 256);
    assert.equal(pickBitrate("mp3", 100), 192);
    assert.equal(pickBitrate("mp3", undefined), 192);
    assert.equal(pickBitrate("flac", 256), null);
  });
});

describe("sizeEstimate", () => {
  test("MP3: kbps times seconds", () => {
    assert.equal(sizeEstimate({ format: "mp3", kbps: 192, seconds: 3600 }), 86_400_000);
  });
  test("WAV: rate times channels times bytes", () => {
    assert.equal(
      sizeEstimate({ format: "wav", bitDepth: 24, seconds: 10, rate: 48000, channels: 2 }),
      2_880_000,
    );
  });
  test("FLAC is about half of WAV", () => {
    assert.equal(
      sizeEstimate({ format: "flac", bitDepth: 16, seconds: 10, rate: 48000, channels: 2 }),
      960_000,
    );
  });
  test("no length, no estimate", () => {
    assert.equal(sizeEstimate({ format: "mp3", kbps: 128, seconds: 0 }), null);
  });
});

function start(extra = {}) {
  return startOptions({
    formats: ALL,
    server: null,
    memory: null,
    marks: NO_MARKS,
    project: PROJECT,
    ...extra,
  });
}

describe("startOptions", () => {
  test("nothing remembered: whole mix, WAV 24-bit, no loudness target, no name", () => {
    const o = start();
    assert.equal(o.scope, "whole");
    assert.equal(o.format, "wav");
    assert.equal(o.bitDepth, 24);
    assert.equal(o.kbps, null);
    assert.equal(o.lufs, null);
    assert.equal(o.name, "");
    assert.deepEqual(o.trackIds, ["a", "b", "c"]);
  });
  test("the server's remembered settings fill the form", () => {
    const o = start({
      server: { mix: { format: "mp3", bit_depth: 24, mp3_kbps: 256, master_lufs: -16 } },
    });
    assert.equal(o.format, "mp3");
    assert.equal(o.kbps, 256);
    assert.equal(o.lufs, -16);
    assert.equal(o.bitDepth, 24);
  });
  test("a remembered format the server no longer offers falls back to the first", () => {
    assert.equal(start({ server: { mix: { format: "ogg" } } }).format, "wav");
  });
  test("the remembered scope applies when it can", () => {
    const o = start({
      memory: { scope: "range", track_ids: ["a", "zz"], ask: false },
      marks: MARKS,
    });
    assert.equal(o.scope, "range");
    assert.equal(o.ask, false);
    assert.deepEqual(o.trackIds, ["a"]);
  });
  test("a remembered range without marks is the whole mix", () => {
    assert.equal(start({ memory: { scope: "range" } }).scope, "whole");
  });
  test("with marks set and nothing remembered, the range is not chosen for you", () => {
    assert.equal(start({ marks: MARKS }).scope, "whole");
  });
  test("remembered tracks that are gone: all tracks are checked again", () => {
    const o = start({ memory: { scope: "tracks", track_ids: ["zz"] } });
    assert.deepEqual(o.trackIds, ["a", "b", "c"]);
  });
});

describe("validateOptions", () => {
  test("the defaults are valid", () => {
    assert.deepEqual(validateOptions(start({ marks: MARKS }), { marks: MARKS }), []);
  });
  test("a range needs marks", () => {
    assert.deepEqual(validateOptions({ ...start(), scope: "range" }, { marks: NO_MARKS }), [
      "ui.exportdialog.err_range",
    ]);
  });
  test("tracks need at least one track", () => {
    assert.deepEqual(
      validateOptions({ ...start(), scope: "tracks", trackIds: [] }, { marks: MARKS }),
      ["ui.exportdialog.err_tracks"],
    );
  });
  test("a loudness target is a number between -70 and 0", () => {
    for (const lufs of [Number.NaN, -80, 3]) {
      assert.deepEqual(validateOptions({ ...start(), lufs }, { marks: MARKS }), [
        "ui.exportdialog.err_lufs",
      ]);
    }
    assert.deepEqual(validateOptions({ ...start(), lufs: -18 }, { marks: MARKS }), []);
  });
});

describe("exportBody", () => {
  test("the whole mix", () => {
    assert.deepEqual(exportBody(start(), MARKS), {
      what: "mix",
      ask: start().ask,
      body: { format: "wav", bit_depth: 24, master_lufs: null },
    });
  });
  test("the in/out range", () => {
    const { body, what } = exportBody({ ...start(), scope: "range" }, MARKS);
    assert.equal(what, "mix");
    assert.deepEqual(body.range, [48000, 144000]);
  });
  test("MP3 sends the bitrate and no bit depth; the name only when typed", () => {
    const o = { ...start(), format: "mp3", kbps: 160, name: "  Cut  " };
    const { body } = exportBody(o, MARKS);
    assert.equal(body.kbps, 160);
    assert.equal("bit_depth" in body, false);
    assert.equal(body.name, "Cut");
    assert.equal("name" in exportBody(start(), MARKS).body, false);
  });
  test("a loudness target is sent; off is sent as null so it clears the remembered one", () => {
    assert.equal(exportBody({ ...start(), lufs: -16 }, MARKS).body.master_lufs, -16);
    assert.equal(exportBody({ ...start(), lufs: null }, MARKS).body.master_lufs, null);
  });
  test("selected tracks are stems: the ids, no loudness target, no range", () => {
    const o = { ...start(), scope: "tracks", trackIds: ["a", "c"], lufs: -16 };
    const { what, body } = exportBody(o, MARKS);
    assert.equal(what, "tracks");
    assert.deepEqual(body.track_ids, ["a", "c"]);
    assert.equal("master_lufs" in body, false);
    assert.equal("range" in body, false);
  });
  test("the all-tracks dialog sends no track ids", () => {
    const { what, body } = exportBody({ ...start(), scope: "alltracks" }, MARKS);
    assert.equal(what, "tracks");
    assert.equal("track_ids" in body, false);
  });
  test("a folder is never in the body: the app asks for it", () => {
    assert.equal("folder" in exportBody(start(), MARKS).body, false);
  });
});

describe("mergeMemory", () => {
  test("keeps the scope, the tracks and whether to ask; not the name", () => {
    const o = { scope: "tracks", trackIds: ["a"], ask: false, name: "x" };
    assert.deepEqual(mergeMemory(null, o), { scope: "tracks", track_ids: ["a"], ask: false });
  });
  test("the all-tracks export does not change the mix's scope", () => {
    const before = { scope: "range", track_ids: ["b"], ask: true };
    assert.deepEqual(mergeMemory(before, { scope: "alltracks", ask: false }), {
      scope: "range",
      track_ids: ["b"],
      ask: false,
    });
  });
});

describe("quickPlan (Cmd+E)", () => {
  test("nothing remembered: the whole mix with the server's remembered settings", () => {
    assert.deepEqual(quickPlan({ memory: null, marks: NO_MARKS, project: PROJECT }), {
      what: "mix",
      body: {},
      scope: "whole",
    });
  });
  test("a remembered range uses the marks now on screen", () => {
    const plan = quickPlan({ memory: { scope: "range" }, marks: MARKS, project: PROJECT });
    assert.deepEqual(plan, { what: "mix", body: { range: [48000, 144000] }, scope: "range" });
  });
  test("a remembered range with no marks asks instead of exporting the wrong thing", () => {
    const plan = quickPlan({ memory: { scope: "range" }, marks: NO_MARKS, project: PROJECT });
    assert.deepEqual(plan, { dialog: "ui.exportdialog.err_range" });
  });
  test("remembered tracks export those that still exist", () => {
    const plan = quickPlan({
      memory: { scope: "tracks", track_ids: ["a", "zz"] },
      marks: NO_MARKS,
      project: PROJECT,
    });
    assert.deepEqual(plan, { what: "tracks", body: { track_ids: ["a"] }, scope: "tracks" });
  });
  test("remembered tracks that are all gone ask", () => {
    const plan = quickPlan({
      memory: { scope: "tracks", track_ids: ["zz"] },
      marks: NO_MARKS,
      project: PROJECT,
    });
    assert.deepEqual(plan, { dialog: "ui.exportdialog.err_tracks" });
  });
  test("Export in/out range ignores the memory", () => {
    const plan = quickPlan({
      memory: { scope: "tracks", track_ids: ["a"] },
      marks: MARKS,
      project: PROJECT,
      force: "range",
    });
    assert.deepEqual(plan, { what: "mix", body: { range: [48000, 144000] }, scope: "range" });
  });
  test("Export in/out range without marks says so", () => {
    const plan = quickPlan({ memory: null, marks: NO_MARKS, project: PROJECT, force: "range" });
    assert.deepEqual(plan, { dialog: "ui.exportdialog.err_range" });
  });
});
