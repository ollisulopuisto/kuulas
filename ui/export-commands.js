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

/**
 * `app`: getState, toast(text, { undo }), download(path, fallbackName) -> Promise<name | null>,
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
  registry.register("export.regions", () => void app.exportRegions(), {
    can: hasRegions,
    hintKey: "cmd.export.regions.hint",
  });
}
