import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import {
  CHAPTER_EXPORTS,
  EXPORT_FORMAT_IDS,
  EXPORTS,
  exportNotice,
  filenameFromDisposition,
  registerExportCommands,
  tracksNotice,
} from "../export-commands.js";

function setup(current) {
  const registry = createRegistry();
  const calls = { downloads: [], toasts: [] };
  registerExportCommands(registry, {
    t: (key, values = {}) => `${key}${JSON.stringify(values)}`,
    app: {
      getState: () => current,
      toast: (text, options) => calls.toasts.push([text, options]),
      download: async (path, fallback) => {
        calls.downloads.push([path, fallback]);
        return fallback;
      },
    },
  });
  return { registry, calls };
}

describe("export commands", () => {
  test("four commands, each tied to its route", () => {
    assert.deepEqual(
      EXPORTS.map((e) => [e.id, e.path]),
      [
        ["export.subtitles_srt", "/api/subtitles?format=srt"],
        ["export.subtitles_vtt", "/api/subtitles?format=vtt"],
        ["export.transcript_txt", "/api/transcript-text?format=txt"],
        ["export.transcript_md", "/api/transcript-text?format=md"],
      ],
    );
  });

  test("they are disabled without a transcript and enabled with one", () => {
    const { registry } = setup({});
    for (const { id } of EXPORTS) {
      assert.equal(registry.status(id), "ready", id);
      assert.equal(registry.can(id, { project: {}, words: [] }), false, id);
      assert.equal(registry.can(id, { project: {} }), false, id);
      assert.equal(registry.can(id, { project: {}, words: [{ w: "a" }] }), true, id);
    }
  });

  test("running one downloads its route and says so", async () => {
    const current = { project: {}, words: [{ w: "a" }] };
    const { registry, calls } = setup(current);
    registry.run("export.transcript_md", null, current);
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(calls.downloads, [["/api/transcript-text?format=md", "transcript.md"]]);
    assert.match(calls.toasts[0][0], /^ui\.export\.done/);
    assert.deepEqual(calls.toasts[0][1], { undo: false });
  });

  test("with no transcript a run does nothing", () => {
    const current = { project: {}, words: [] };
    const { registry, calls } = setup(current);
    assert.equal(registry.run("export.subtitles_srt", null, current), false);
    assert.equal(calls.downloads.length, 0);
  });
});

describe("filenameFromDisposition", () => {
  test("reads the quoted name, else the fallback", () => {
    assert.equal(
      filenameFromDisposition('attachment; filename="subtitles.srt"', "x"),
      "subtitles.srt",
    );
    assert.equal(filenameFromDisposition(null, "x.txt"), "x.txt");
    assert.equal(filenameFromDisposition("inline", "x.txt"), "x.txt");
  });
});

describe("export all tracks", () => {
  const withTracks = { project: { tracks: [{ id: "a" }], markers: [] } };
  const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;

  test("needs a track and starts the one-button export", () => {
    const registry = createRegistry();
    const started = [];
    registerExportCommands(registry, {
      t,
      app: { getState: () => withTracks, toast: () => {}, exportTracks: () => started.push(1) },
    });
    assert.equal(registry.can("export.tracks", { project: { tracks: [] } }), false);
    assert.equal(registry.can("export.tracks", {}), false);
    assert.equal(registry.run("export.tracks", null, withTracks), true);
    assert.equal(started.length, 1);
  });

  test("progress, done, silent, failed and cancelled each have their own notice", () => {
    const running = tracksNotice({ state: "running", progress: 0.456 }, t);
    assert.deepEqual(
      [running.kind, running.sticky, running.cancel, running.text],
      ["ok", true, true, 'ui.export.tracks_running{"percent":46}'],
    );
    const result = { path: "/x/Main 1", track_count: 3, silent: [] };
    const done = tracksNotice({ state: "completed", result }, t);
    assert.equal(done.text, 'ui.export.tracks_done{"count":3,"path":"/x/Main 1"}');
    assert.equal(done.reveal, true);
    const quiet = tracksNotice(
      { state: "completed", result: { ...result, silent: ["B", "C"] } },
      t,
    );
    assert.equal(
      quiet.text,
      'ui.export.tracks_done_silent{"count":3,"path":"/x/Main 1","silent":"B, C"}',
    );
    const failed = tracksNotice({ state: "failed", error: { text: "Disk full" } }, t);
    assert.deepEqual([failed.kind, failed.text], ["error", "Disk full"]);
    assert.equal(tracksNotice({ state: "cancelled" }, t).text, "ui.export.cancelled{}");
    assert.equal(tracksNotice({ state: "queued", progress: 0 }, t).cancel, true);
  });
});

describe("chapter and region exports (WP19h)", () => {
  const withChapters = { project: { markers: [{ id: "a", kind: "chapter", start: 0 }] } };

  test("chapter exports need a chapter marker, and download their route", async () => {
    const { registry, calls } = setup(withChapters);
    assert.equal(registry.can("export.chapters_text", { project: { markers: [] } }), false);
    assert.equal(
      registry.can("export.chapters_json", { project: { markers: [{ kind: "marker" }] } }),
      false,
    );
    registry.run("export.chapters_json", null, withChapters);
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(calls.downloads, [["/api/chapters?style=json", "chapters.json"]]);
    assert.equal(CHAPTER_EXPORTS.length, 2);
  });

  test("Export regions needs a region and queues the job", () => {
    const state = { project: { markers: [{ id: "r", kind: "region", start: 0, end: 9 }] } };
    const registry = createRegistry();
    const queued = [];
    registerExportCommands(registry, {
      t: (key) => key,
      app: {
        getState: () => state,
        toast: () => {},
        download: async () => null,
        exportRegions: () => queued.push(1),
      },
    });
    assert.equal(registry.can("export.regions", { project: { markers: [] } }), false);
    assert.equal(registry.run("export.regions", null, state), true);
    assert.equal(queued.length, 1);
  });
});

describe("export formats", () => {
  const withTracks = { project: { tracks: [{ id: "a" }], markers: [] } };
  const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;

  function formatSetup(available) {
    const registry = createRegistry();
    const started = [];
    registerExportCommands(registry, {
      t,
      app: {
        getState: () => withTracks,
        toast: () => {},
        exportFormats: () => available,
        exportTracks: (format) => started.push(["tracks", format]),
        exportMix: (format) => started.push(["mix", format]),
      },
    });
    return { registry, started };
  }

  test("the ids are the registry's, WAV first", () => {
    assert.deepEqual(EXPORT_FORMAT_IDS, ["wav", "flac", "mp3", "aiff", "m4a", "opus", "ogg"]);
  });

  test("every format has a mix command and an all-tracks command", () => {
    const { registry } = formatSetup(EXPORT_FORMAT_IDS);
    for (const id of EXPORT_FORMAT_IDS) {
      for (const prefix of ["export.mix_", "export.tracks_"]) {
        assert.equal(registry.status(prefix + id), "ready", prefix + id);
        assert.equal(registry.hintKey(prefix + id), `cmd.${prefix}${id}.hint`);
      }
    }
  });

  test("a format the server does not offer is disabled", () => {
    const { registry } = formatSetup(["wav", "flac"]);
    assert.equal(registry.can("export.mix_flac", withTracks), true);
    assert.equal(registry.can("export.mix_m4a", withTracks), false);
    assert.equal(registry.can("export.tracks_opus", withTracks), false);
    assert.equal(registry.can("export.mix_wav", { project: { tracks: [] } }), false);
  });

  test("running one starts the job with that format", () => {
    const { registry, started } = formatSetup(EXPORT_FORMAT_IDS);
    registry.run("export.mix_m4a", null, withTracks);
    registry.run("export.tracks_aiff", null, withTracks);
    assert.deepEqual(started, [
      ["mix", "m4a"],
      ["tracks", "aiff"],
    ]);
  });

  test("the one-button tracks export stays WAV and needs no format", () => {
    const { registry, started } = formatSetup(["wav"]);
    registry.run("export.tracks", null, withTracks);
    assert.deepEqual(started, [["tracks", undefined]]);
  });

  test("the mix has its own progress and done notices", () => {
    const running = exportNotice({ state: "running", progress: 0.5 }, t, "mix");
    assert.equal(running.text, 'ui.export.mix_running{"percent":50}');
    assert.equal(running.cancel, true);
    const done = exportNotice({ state: "completed", result: { path: "/x/Main.flac" } }, t, "mix");
    assert.equal(done.text, 'ui.export.mix_done{"path":"/x/Main.flac"}');
    assert.equal(done.reveal, true);
  });
});
