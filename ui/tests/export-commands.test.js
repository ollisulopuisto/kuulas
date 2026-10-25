import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import {
  CHAPTER_EXPORTS,
  EXPORT_FORMAT_IDS,
  EXPORTS,
  exportNotice,
  exportRequest,
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
    assert.equal(
      filenameFromDisposition(
        "attachment; filename=\"P__ editio chapters.txt\"; filename*=UTF-8''P%C3%A4%C3%A4%20chapters.txt",
        "x",
      ),
      "Pää chapters.txt",
    );
    assert.equal(filenameFromDisposition(null, "x.txt"), "x.txt");
    assert.equal(filenameFromDisposition("inline", "x.txt"), "x.txt");
  });
});

describe("export all tracks", () => {
  const withTracks = { project: { tracks: [{ id: "a" }], markers: [] } };
  const t = (key, values = {}) => `${key}${JSON.stringify(values)}`;

  test("needs a track; the plain command exports at once, the (options) one opens the dialog", () => {
    const registry = createRegistry();
    const started = [];
    registerExportCommands(registry, {
      t,
      app: {
        getState: () => withTracks,
        toast: () => {},
        exportTracks: (format, options) => started.push(["tracks", format, options]),
        openExportDialog: (what) => started.push(["dialog", what]),
      },
    });
    for (const id of ["export.tracks", "export.tracks_quick"]) {
      assert.equal(registry.can(id, { project: { tracks: [] } }), false, id);
      assert.equal(registry.can(id, {}), false, id);
    }
    assert.equal(registry.run("export.tracks_quick", null, withTracks), true);
    assert.equal(registry.run("export.tracks", null, withTracks), true);
    assert.deepEqual(started, [
      ["tracks", undefined, { ask: false }],
      ["dialog", "tracks"],
    ]);
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

describe("the cut list export", () => {
  test("it needs a track, and downloads the cut list", async () => {
    const withTrack = { project: { tracks: [{ id: "t", clips: [] }] } };
    const { registry, calls } = setup(withTrack);
    assert.equal(registry.can("export.cut_list", { project: null }), false);
    assert.equal(registry.can("export.cut_list", { project: { tracks: [] } }), false);
    registry.run("export.cut_list", null, withTrack);
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(calls.downloads, [["/api/cut-list", "cut-list.json"]]);
    assert.equal(registry.hintKey("export.cut_list"), "cmd.export.cut_list.hint");
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

describe("asking where to export", () => {
  const withTracks = { project: { tracks: [{ id: "a" }], markers: [] } };
  const t = (key) => key;
  const hint = async () => ({ folder: "/p/Ep exports", remembered: false });

  function setup() {
    const registry = createRegistry();
    const started = [];
    registerExportCommands(registry, {
      t,
      app: {
        getState: () => withTracks,
        toast: () => {},
        exportFormats: () => EXPORT_FORMAT_IDS,
        exportTracks: (format, options) => started.push(["tracks", format, options]),
        exportMix: (format, options) => started.push(["mix", format, options]),
        exportQuick: (force) => started.push(["quick", force]),
      },
    });
    return { registry, started };
  }

  test("the per-format commands ask, the quick ones do not", () => {
    const { registry, started } = setup();
    registry.run("export.tracks_flac", null, withTracks);
    registry.run("export.mix_mp3", null, withTracks);
    registry.run("export.tracks_quick", null, withTracks);
    registry.run("app.export", null, withTracks);
    // Cmd+E goes through the quick export: the last scope and settings of this project.
    assert.deepEqual(started, [
      ["tracks", "flac", { ask: true }],
      ["mix", "mp3", { ask: true }],
      ["tracks", undefined, { ask: false }],
      ["quick", undefined],
    ]);
  });

  test("Export in/out range needs tracks and marks, and exports the marked range", () => {
    const { registry, started } = setup();
    const marked = { ...withTracks, inPoint: 100, outPoint: 900 };
    assert.equal(registry.can("export.range", withTracks), false);
    assert.equal(registry.can("export.range", { ...withTracks, inPoint: 100 }), false);
    assert.equal(registry.can("export.range", marked), true);
    assert.equal(
      registry.can("export.range", { project: { tracks: [] }, inPoint: 1, outPoint: 2 }),
      false,
    );
    registry.run("export.range", null, marked);
    assert.deepEqual(started, [["quick", "range"]]);
    assert.equal(registry.hintKey("export.range"), "cmd.export.range.hint");
  });

  test("Export mix (options)… and Export all tracks (options)… open the dialog", () => {
    const registry = createRegistry();
    const opened = [];
    registerExportCommands(registry, {
      t,
      app: { getState: () => withTracks, toast: () => {}, openExportDialog: (w) => opened.push(w) },
    });
    registry.run("export.mix_options", null, withTracks);
    registry.run("export.tracks", null, withTracks);
    assert.deepEqual(opened, ["mix", "tracks"]);
    assert.equal(registry.can("export.mix_options", { project: { tracks: [] } }), false);
    for (const id of ["export.mix_options", "app.export"]) {
      assert.equal(registry.status(id), "ready", id);
      assert.equal(registry.hintKey(id), `cmd.${id}.hint`, id);
    }
  });

  test("the quick command is ready with tracks and has a hint", () => {
    const { registry } = setup();
    assert.equal(registry.status("export.tracks_quick"), "ready");
    assert.equal(registry.hintKey("export.tracks_quick"), "cmd.export.tracks_quick.hint");
    assert.equal(registry.can("export.tracks_quick", { project: { tracks: [] } }), false);
  });

  test("the request carries the chosen folder, starting at the hint", async () => {
    const starts = [];
    const bridge = {
      choose_export_folder: async (start) => {
        starts.push(start);
        return "/chosen";
      },
    };
    const options = await exportRequest({ format: "flac", ask: true, bridge, hint });
    assert.deepEqual(options, { format: "flac", folder: "/chosen" });
    assert.deepEqual(starts, ["/p/Ep exports"]);
  });

  test("cancelling the chooser starts nothing", async () => {
    const bridge = { choose_export_folder: async () => null };
    assert.equal(await exportRequest({ ask: true, bridge, hint }), null);
  });

  test("quick, or no bridge (a plain browser), sends no folder and shows no dialog", async () => {
    let asked = 0;
    const bridge = {
      choose_export_folder: async () => {
        asked++;
        return "/x";
      },
    };
    assert.deepEqual(await exportRequest({ ask: false, bridge, hint }), {});
    assert.deepEqual(await exportRequest({ format: "wav", ask: true, bridge: null, hint }), {
      format: "wav",
    });
    assert.equal(asked, 0);
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

  test("the quick tracks export stays WAV and needs no format", () => {
    const { registry, started } = formatSetup(["wav"]);
    registry.run("export.tracks_quick", null, withTracks);
    assert.deepEqual(started, [["tracks", undefined]]);
  });

  test("while a selection exports, the running notice says so first", () => {
    const lead = "Exporting the selection only: 00.12-00.18";
    const running = exportNotice({ state: "running", progress: 0.5 }, t, "mix", lead);
    assert.equal(running.text, `${lead} ui.export.mix_running{"percent":50}`);
    const done = exportNotice(
      { state: "completed", result: { path: "/x/a.flac" } },
      t,
      "mix",
      lead,
    );
    assert.equal(done.text.includes(lead), false);
  });

  test("the mix has its own progress and done notices", () => {
    const running = exportNotice({ state: "running", progress: 0.5 }, t, "mix");
    assert.equal(running.text, 'ui.export.mix_running{"percent":50}');
    assert.equal(running.cancel, true);
    const done = exportNotice({ state: "completed", result: { path: "/x/Main.flac" } }, t, "mix");
    assert.equal(done.text, 'ui.export.mix_done{"path":"/x/Main.flac"}');
    assert.equal(done.reveal, true);
  });

  test("the done notice says what was exported: whole mix, range, silent tracks", () => {
    const text = (result) =>
      exportNotice({ state: "completed", result: { path: "/x/a.mp3", ...result } }, t, "mix").text;
    assert.equal(text({ settings: {} }), 'ui.export.mix_done{"path":"/x/a.mp3"}');
    assert.equal(
      text({ settings: { range: [1, 2] } }),
      'ui.export.mix_done_range{"path":"/x/a.mp3"}',
    );
    assert.equal(
      text({ settings: {}, silent: ["Ville", "Maija"] }),
      'ui.export.mix_done_silent{"path":"/x/a.mp3","silent":"Ville, Maija"}',
    );
    assert.equal(
      text({ settings: { range: [1, 2] }, silent: ["Ville"] }),
      'ui.export.mix_done_range_silent{"path":"/x/a.mp3","silent":"Ville"}',
    );
  });

  test("a stem export of a range says so", () => {
    const done = exportNotice(
      {
        state: "completed",
        result: { path: "/x/d", track_count: 2, settings: { range: [1, 2] }, silent: [] },
      },
      t,
      "tracks",
    );
    assert.equal(done.text, 'ui.export.tracks_done_range{"count":2,"path":"/x/d"}');
  });
});

describe("Music report (WP25)", () => {
  const state = { project: { tracks: [{ id: "m", kind: "music" }], markers: [] } };

  test("Music report… needs a project, opens the dialog and has a hint", () => {
    const registry = createRegistry();
    const opened = [];
    registerExportCommands(registry, {
      t: (key) => key,
      app: { getState: () => state, toast: () => {}, openMusicReport: () => opened.push(1) },
    });
    assert.equal(registry.can("export.music_report", { project: null }), false);
    assert.equal(registry.can("export.music_report", state), true);
    assert.equal(registry.run("export.music_report", null, state), true);
    assert.deepEqual(opened, [1]);
    assert.equal(registry.hintKey("export.music_report"), "cmd.export.music_report.hint");
  });
});
