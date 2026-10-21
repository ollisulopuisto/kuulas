// File > Export subtitles / transcript: four downloads from the server. They need a
// transcript, so they are disabled without one. The desktop bridge (desktop.py) has a save
// dialog (pick_save) but no way to write a file, so both the browser and the desktop window
// use the browser download.

import { hasRange } from "./export-dialog-model.js";
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
  // filename* (RFC 5987) holds the real UTF-8 name; filename="" is its ASCII fallback.
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header ?? "");
  if (star) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      // fall through to the plain name
    }
  }
  const match = /filename="([^"]+)"/.exec(header ?? "");
  return match ? match[1] : fallback;
}

const hasTranscript = (state) => Boolean(state?.project) && (state?.words?.length ?? 0) > 0;

const hasChapters = (state) => Boolean(state?.project) && chapterCount(state.project.markers) > 0;
const hasRegions = (state) => Boolean(state?.project) && regionCount(state.project.markers) > 0;

const hasTracks = (state) => (state?.project?.tracks?.length ?? 0) > 0;
const hasMarkedRange = (state) => hasTracks(state) && hasRange(state);

// The formats the server can write (GET /api/export-formats), in the registry's order:
// src/kuulas/export_formats.py (tests/test_export_formats.py checks the two agree). Each
// has a mix command export.mix_<id> and an all-tracks command export.tracks_<id>; the menus
// list the ones the server offers, and the commands are disabled for the others.
export const EXPORT_FORMAT_IDS = ["wav", "flac", "mp3", "aiff", "m4a", "opus", "ogg"];
/** WAV, FLAC and AIFF need no codec; WAV and FLAC need not even ffmpeg. */
export const ALWAYS_AVAILABLE = ["wav", "flac"];

/**
 * What the notice says about an export job (as /api/jobs lists it), `kind` "tracks" (the
 * default) or "mix": { kind, text, sticky, cancel, reveal }. `sticky` stays until replaced,
 * `cancel` offers Cancel, `reveal` offers Show in Finder (desktop window only; the caller
 * checks). `selectionText` (selectionNotice) leads the running text of a selection export.
 */
export function exportNotice(job, t, what = "tracks", selectionText = "") {
  if (job.state === "completed") {
    const { path, track_count: count, silent = [], settings } = job.result ?? {};
    const range = settings?.range ? "_range" : "";
    let text;
    if (what === "mix") {
      // Says what was exported: the whole mix or the in/out range, and which tracks are silent.
      text =
        silent.length > 0
          ? t(`ui.export.mix_done${range}_silent`, { path, silent: silent.join(", ") })
          : t(`ui.export.mix_done${range}`, { path });
    } else if (silent.length > 0) {
      text = t("ui.export.tracks_done_silent", { count, path, silent: silent.join(", ") });
    } else text = t(`ui.export.tracks_done${range}`, { count, path });
    return { kind: "ok", text, sticky: true, cancel: false, reveal: true };
  }
  if (job.state === "failed") {
    return { kind: "error", text: job.error?.text ?? "", sticky: false, cancel: false };
  }
  if (job.state === "cancelled") {
    return { kind: "ok", text: t("ui.export.cancelled"), sticky: false, cancel: false };
  }
  const percent = Math.round((job.progress ?? 0) * 100);
  const running = t(what === "mix" ? "ui.export.mix_running" : "ui.export.tracks_running", {
    percent,
  });
  return {
    kind: "ok",
    // A selection export says so first: what is exported, which tracks and span.
    text: selectionText ? `${selectionText} ${running}` : running,
    sticky: true,
    cancel: true,
  };
}

/** The "Export all tracks" notice (see exportNotice). */
export const tracksNotice = (job, t) => exportNotice(job, t, "tracks");

/**
 * The body of an export request, or null when the owner cancelled. In the desktop window
 * (`bridge` has choose_export_folder) and when `ask`, a native folder chooser opens first,
 * starting at `hint()` ({ folder }: the remembered folder or `<project> exports`); the chosen
 * folder is the parent the server puts the export's own sub-folder / file in. Without a
 * bridge (plain browser) or when not asking, no folder is sent and the server uses the
 * remembered or default one.
 */
export async function exportRequest({ format, ask, bridge, hint, onAsk }) {
  const options = format ? { format } : {};
  if (!ask || typeof bridge?.choose_export_folder !== "function") return options;
  const { folder: start } = await hint();
  onAsk?.();
  const folder = await bridge.choose_export_folder(start);
  return folder ? { ...options, folder } : null;
}

/**
 * `app`: getState, toast(text, { undo }), download(path, fallbackName) -> Promise<name | null>,
 * exportTracks(format?, { ask }) -> Promise (asks for a folder when `ask`, then starts the track export, WAV unless a format id is given,
 * and follows its job), exportMix(format, { ask }) -> Promise (the same for the mix),
 * exportQuick(force?) -> Promise (the quick mix export with the project's last scope and
 * settings; `force` "range" exports the marked range whatever was remembered),
 * exportFormats() -> the ids of the formats the server offers (null until fetched),
 * openExportDialog("mix" | "tracks") -> opens the "(options)…" dialog (export-dialog.js),
 * exportRegions() -> Promise (queues the one region job; the jobs list shows its progress),
 * automix() -> opens the "Mix with the automixer" dialog (WP68),
 * automixLog() -> opens the live "Automixer log" viewer.
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
  // File menu (WP74): the plain commands export at once, into the remembered folder or
  // `<project> exports` beside the project, without asking; the "(options)…" ones open the dialog
  // (format, and whether to choose the folder first, in the desktop window).
  // Mod+E exports at once with what this project exported last: the same scope (whole mix,
  // in/out range or chosen tracks) and the same settings; the notice says what it exported.
  registry.register("app.export", () => void app.exportQuick(), {
    can: hasTracks,
    hintKey: "cmd.app.export.hint",
  });
  registry.register("export.range", () => void app.exportQuick("range"), {
    can: hasMarkedRange,
    hintKey: "cmd.export.range.hint",
  });
  registry.register("export.mix_options", () => app.openExportDialog("mix"), {
    can: hasTracks,
    hintKey: "cmd.export.mix_options.hint",
  });
  registry.register("export.tracks", () => app.openExportDialog("tracks"), {
    can: hasTracks,
    hintKey: "cmd.export.tracks.hint",
  });
  registry.register("export.tracks_quick", () => void app.exportTracks(undefined, { ask: false }), {
    can: hasTracks,
    hintKey: "cmd.export.tracks_quick.hint",
  });
  const offered = () => app.exportFormats?.() ?? ALWAYS_AVAILABLE;
  for (const format of EXPORT_FORMAT_IDS) {
    const can = (state) => hasTracks(state) && offered().includes(format);
    registry.register(`export.mix_${format}`, () => void app.exportMix(format, { ask: true }), {
      can,
      hintKey: `cmd.export.mix_${format}.hint`,
    });
    registry.register(
      `export.tracks_${format}`,
      () => void app.exportTracks(format, { ask: true }),
      {
        can,
        hintKey: `cmd.export.tracks_${format}.hint`,
      },
    );
  }
  registry.register("export.automix", () => void app.automix(), {
    can: hasTracks,
    hintKey: "cmd.export.automix.hint",
  });
  registry.register("export.automix_log", () => void app.automixLog(), {
    hintKey: "cmd.export.automix_log.hint",
  });
  registry.register("export.regions", () => void app.exportRegions(), {
    can: hasRegions,
    hintKey: "cmd.export.regions.hint",
  });
}
