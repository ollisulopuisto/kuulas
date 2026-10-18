import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRegistry } from "../commands.js";
import {
  CHAPTER_EXPORTS,
  EXPORTS,
  filenameFromDisposition,
  registerExportCommands,
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
