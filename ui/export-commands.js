// File > Export subtitles / transcript: four downloads from the server. They need a
// transcript, so they are disabled without one. The desktop bridge (desktop.py) has a save
// dialog (pick_save) but no way to write a file, so both the browser and the desktop window
// use the browser download.

import { chapterCount, regionCount } from "./markers-model.js";

export const EXPORTS = [
  { id: "export.subtitles_srt", path: "/api/subtitles?format=srt", file: "subtitles.srt" },
  { id: "export.subtitles_vtt", path: "/api/subtitles?format=vtt", file: "subtitles.vtt" },
  { id: "export.transcript_txt", path: "/api/transcript-text?format=txt", file: "transcript.txt" },
  { id: "export.transcript_md", path: "/api/transcript-text?format=md", file: "transcript.md" },
];

// Chapter lists (WP19h): the markers of kind chapter as text or Podcasting 2.0 JSON.
export const CHAPTER_EXPORTS = [
  { id: "export.chapters_text", path: "/api/chapters?style=text", file: "chapters.txt" },
  { id: "export.chapters_json", path: "/api/chapters?style=json", file: "chapters.json" },
];

/** The file name in a Content-Disposition header, else the fallback. */
export function filenameFromDisposition(header, fallback) {
  const match = /filename="([^"]+)"/.exec(header ?? "");
  return match ? match[1] : fallback;
}

const hasTranscript = (state) => Boolean(state?.project) && (state?.words?.length ?? 0) > 0;

const hasChapters = (state) => Boolean(state?.project) && chapterCount(state.project.markers) > 0;
const hasRegions = (state) => Boolean(state?.project) && regionCount(state.project.markers) > 0;

const hasTracks = (state) => (state?.project?.tracks?.length ?? 0) > 0;

/**
 * What the notice says about the "Export all tracks" job (as /api/jobs lists it):
 * { kind, text, sticky, cancel, reveal }. `sticky` stays until replaced, `cancel` offers
 * Cancel, `reveal` offers Show in Finder (desktop window only; the caller checks).
 */
export function tracksNotice(job, t) {
  if (job.state === "completed") {
    const { path, track_count: count, silent = [] } = job.result ?? {};
    const text =
      silent.length > 0
        ? t("ui.export.tracks_done_silent", { count, path, silent: silent.join(", ") })
        : t("ui.export.tracks_done", { count, path });
    return { kind: "ok", text, sticky: true, cancel: false, reveal: true };
  }
  if (job.state === "failed") {
    return { kind: "error", text: job.error?.text ?? "", sticky: false, cancel: false };
  }
  if (job.state === "cancelled") {
    return { kind: "ok", text: t("ui.export.cancelled"), sticky: false, cancel: false };
  }
  const percent = Math.round((job.progress ?? 0) * 100);
  return {
    kind: "ok",
    text: t("ui.export.tracks_running", { percent }),
    sticky: true,
    cancel: true,
  };
}

/**
 * `app`: getState, toast(text, { undo }), download(path, fallbackName) -> Promise<name | null>,
 * exportTracks() -> Promise (starts the one-button track export and follows its job),
 * exportRegions() -> Promise (queues the one region job; the jobs list shows its progress).
 */
export function registerExportCommands(registry, { app, t }) {
  for (const { id, path, file } of EXPORTS) {
    registry.register(
      id,
      async () => {
        const name = await app.download(path, file);
        if (name) app.toast(t("ui.export.done", { name }), { undo: false });
      },
      { can: hasTranscript, hintKey: `cmd.${id}.hint` },
    );
  }
  for (const { id, path, file } of CHAPTER_EXPORTS) {
    registry.register(
      id,
      async () => {
        const name = await app.download(path, file);
        if (name) app.toast(t("ui.export.done", { name }), { undo: false });
      },
      { can: hasChapters, hintKey: `cmd.${id}.hint` },
    );
  }
  registry.register("export.tracks", () => void app.exportTracks(), {
    can: hasTracks,
    hintKey: "cmd.export.tracks.hint",
  });
  registry.register("export.regions", () => void app.exportRegions(), {
    can: hasRegions,
    hintKey: "cmd.export.regions.hint",
  });
}
