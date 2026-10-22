// The "(options)…" export dialog (WP11, WP74): what it offers and what it asks the export for.
// File > Export mix (options)… chooses what to export (the whole mix, the in/out range, or some
// tracks as stems), the format and its quality, a loudness target, a name and the folder.
// Export all tracks (options)… keeps the old small form (format, depth, folder). All pure; the
// DOM is export-dialog.js and the request goes through app.js.

import { ALWAYS_AVAILABLE } from "./export-commands.js";
import { selectionBody } from "./export-selection-model.js";

const FALLBACK = { wav: "WAV", flac: "FLAC" };

/**
 * The formats the dialog lists: the server's ([{ id, label }], its order), or WAV and FLAC (which
 * need no codec) while the server has not answered.
 */
export function dialogFormats(offered) {
  if (Array.isArray(offered) && offered.length > 0) return offered;
  return ALWAYS_AVAILABLE.map((id) => ({ id, label: FALLBACK[id] ?? id }));
}

/**
 * The format to preselect: the remembered one when it is listed, else FLAC (lossless, about half
 * the size of WAV, and every tool takes it), else the first listed.
 */
export function pickFormat(formats, remembered) {
  if (formats.some((format) => format.id === remembered)) return remembered;
  if (formats.some((format) => format.id === "flac")) return "flac";
  return formats[0]?.id ?? "flac";
}

// -- marks and tracks ----------------------------------------------------------------------

/** Is there an in/out range: both marks set, the out after the in. */
export function hasRange({ inPoint, outPoint } = {}) {
  return typeof inPoint === "number" && typeof outPoint === "number" && outPoint > inPoint;
}

/**
 * The tracks that come out as silence, by the mixer's rule (transcript.silent_tracks on the
 * server): while anything is soloed only soloed tracks sound, otherwise the mute switch decides,
 * and a muted bus silences its tracks. -> [{ id, name }] in track order.
 */
export function silentTracks(project) {
  const tracks = project?.tracks ?? [];
  const soloing = tracks.some((track) => track.solo);
  const mutedBuses = new Set((project?.buses ?? []).filter((bus) => bus.mute).map((bus) => bus.id));
  return tracks
    .filter((track) => (soloing ? !track.solo : track.mute) || mutedBuses.has(track.bus))
    .map((track) => ({ id: track.id, name: track.name }));
}

// -- loudness --------------------------------------------------------------------------------

/** Target loudness presets; `lufs` null is "do not change the loudness". */
export const LUFS_PRESETS = [
  { id: "off", lufs: null },
  { id: "podcast", lufs: -16 },
  { id: "streaming", lufs: -14 },
  { id: "broadcast", lufs: -23 },
];

/** The preset id of a target, or "custom". */
export function lufsPresetOf(lufs) {
  const preset = LUFS_PRESETS.find((item) => item.lufs === (lufs ?? null));
  return preset ? preset.id : "custom";
}

// -- depth, bitrate, size ----------------------------------------------------------------------

const DEPTHS = { wav: [16, 24, 32], flac: [16, 24], aiff: [16, 24, 32] };
// Constant bitrates offered per lossy format; the first two numbers of DEFAULT_KBPS are the
// server's default for (mono, stereo), src/kuulas/export_formats.py.
const BITRATES = {
  mp3: [128, 160, 192, 256, 320],
  m4a: [96, 128, 160, 192, 256],
  opus: [32, 48, 64, 96, 128],
  ogg: [96, 128, 160, 192, 256],
};
const DEFAULT_KBPS = { mp3: [128, 192], m4a: [96, 160], opus: [48, 96], ogg: [96, 160] };

/** The bit depths a PCM format takes ([] for the lossy ones). */
export const depthChoices = (format) => DEPTHS[format] ?? [];
/** The remembered depth when the format takes it, else 24. */
export function pickDepth(format, remembered) {
  const choices = depthChoices(format);
  if (choices.length === 0) return 24;
  return choices.includes(remembered) ? remembered : 24;
}
/** The bitrates (kbps) a lossy format offers ([] for the others). */
export const bitrateChoices = (format) => BITRATES[format] ?? [];
/** The server's default bitrate for the channels, or null for a format without one. */
export function defaultBitrate(format, channels = 2) {
  const pair = DEFAULT_KBPS[format];
  return pair ? pair[channels === 1 ? 0 : 1] : null;
}
/** The remembered bitrate when this format offers it, else its default. */
export function pickBitrate(format, remembered, channels = 2) {
  if (bitrateChoices(format).length === 0) return null;
  return bitrateChoices(format).includes(remembered)
    ? remembered
    : defaultBitrate(format, channels);
}

/** About how many bytes the file is, or null when it cannot be told. */
export function sizeEstimate({ format, kbps, bitDepth = 24, seconds, rate = 48000, channels = 2 }) {
  if (!(seconds > 0)) return null;
  if (bitrateChoices(format).length > 0) {
    const rateKbps = kbps ?? defaultBitrate(format, channels);
    return Math.round(((rateKbps * 1000) / 8) * seconds);
  }
  const bytes = rate * channels * (bitDepth / 8) * seconds;
  return Math.round(format === "flac" ? bytes / 2 : bytes);
}

// -- the form ------------------------------------------------------------------------------------

const ids = (project) => (project?.tracks ?? []).map((track) => track.id);

/**
 * The form's starting values. `server` is GET /api/export-settings (null until known): its
 * `mix` holds the format, depth, bitrate and loudness target the last export used. `memory` is
 * the per-project scope memory (mergeMemory). `scope` is "whole" | "range" | "tracks"; a range
 * that cannot be had (no marks) is the whole mix. Nothing is chosen for the user that they did
 * not choose before: marks on screen alone do not select the range. The exception is the
 * selection (export-selection-model.js): while one exists "Only export the selection" is
 * ticked, whatever scope was remembered (owner, 2026-10-21).
 */
export function startOptions({ formats, server, memory, marks, project, selection = null }) {
  const last = server?.mix ?? {};
  const list = dialogFormats(formats);
  const format = pickFormat(list, last.format);
  const everyTrack = ids(project);
  const kept = (memory?.track_ids ?? []).filter((id) => everyTrack.includes(id));
  let scope = memory?.scope ?? "whole";
  if (scope === "range" && !hasRange(marks)) scope = "whole";
  if (scope === "tracks" && kept.length === 0) scope = "whole";
  return {
    scope,
    trackIds: kept.length > 0 ? kept : everyTrack,
    format,
    bitDepth: pickDepth(format, last.bit_depth),
    kbps: pickBitrate(format, last.mp3_kbps),
    lufs: typeof last.master_lufs === "number" ? last.master_lufs : null,
    name: "",
    ask: memory?.ask ?? true,
    onlySelection: Boolean(selection),
  };
}

/** The translation keys of what is wrong with the form (empty when it can start). */
export function validateOptions(options, { marks, selection = null }) {
  const errors = [];
  // While the selection decides the range and tracks, the scope's own needs do not matter.
  const decided = Boolean(selection) && options.onlySelection !== false;
  if (!decided && options.scope === "range" && !hasRange(marks)) {
    errors.push("ui.exportdialog.err_range");
  }
  if (!decided && options.scope === "tracks" && (options.trackIds ?? []).length === 0) {
    errors.push("ui.exportdialog.err_tracks");
  }
  if (options.scope !== "tracks" && options.scope !== "alltracks") {
    const { lufs } = options;
    if (lufs !== null && lufs !== undefined && !(lufs >= -70 && lufs <= 0)) {
      errors.push("ui.exportdialog.err_lufs");
    }
  }
  return errors;
}

/**
 * What to ask the server for: { what: "mix" | "tracks", body, ask }. The body never has a
 * folder: the app asks for it (desktop window) or the server uses the remembered one.
 * "tracks" is the stems of the chosen tracks; "alltracks" (the old dialog) all of them.
 */
export function exportBody(options, marks, selection = null) {
  const only = Boolean(selection) && options.onlySelection !== false;
  const stems = options.scope === "tracks" || options.scope === "alltracks";
  const body = { format: options.format };
  if (depthChoices(options.format).length > 0) body.bit_depth = options.bitDepth;
  if (bitrateChoices(options.format).length > 0 && options.kbps) body.kbps = options.kbps;
  if (!stems) body.master_lufs = options.lufs ?? null;
  if (options.scope === "range") body.range = [marks.inPoint, marks.outPoint];
  if (options.scope === "tracks") body.track_ids = [...options.trackIds];
  // The selection replaces the scope's range and tracks (a track list ticked in the dialog
  // included: the selection says which tracks).
  if (only) {
    delete body.range;
    delete body.track_ids;
    Object.assign(body, selectionBody(selection));
  }
  const name = (options.name ?? "").trim();
  if (name) body.name = name;
  return { what: stems ? "tracks" : "mix", body, ask: Boolean(options.ask) };
}

/**
 * The per-project memory after an export from the mix dialog: scope, chosen tracks and whether
 * to ask for the folder (the rest the server remembers). The all-tracks dialog keeps the scope.
 */
export function mergeMemory(previous, options) {
  const base = previous ?? {};
  if (options.scope === "alltracks") {
    return {
      scope: base.scope ?? "whole",
      track_ids: base.track_ids ?? [],
      ask: Boolean(options.ask),
    };
  }
  return {
    scope: options.scope,
    track_ids: [...(options.trackIds ?? base.track_ids ?? [])],
    ask: Boolean(options.ask),
  };
}

/**
 * What Cmd+E does: the last scope of this project with the settings the server remembers.
 * -> { what, body, scope } to export now, or { dialog: key } when the remembered scope cannot
 * be had (no marks, the tracks are gone): the dialog opens and the key says why. `force`
 * "range" is Export in/out range, whatever was remembered. A `selection` (resolved by
 * export-selection-model.js) wins over the remembered scope; only the explicit Export
 * in/out range command ignores it. The plan then carries it for the notice.
 */
export function quickPlan({ memory, marks, project, force, selection = null }) {
  if (selection && !force) {
    const stems = memory?.scope === "tracks";
    return {
      what: stems ? "tracks" : "mix",
      body: selectionBody(selection),
      scope: stems ? "tracks" : "range",
      selection,
    };
  }
  const scope = force ?? memory?.scope ?? "whole";
  if (scope === "range") {
    if (!hasRange(marks)) return { dialog: "ui.exportdialog.err_range" };
    return { what: "mix", body: { range: [marks.inPoint, marks.outPoint] }, scope };
  }
  if (scope === "tracks") {
    const have = ids(project);
    const chosen = (memory?.track_ids ?? []).filter((id) => have.includes(id));
    if (chosen.length === 0) return { dialog: "ui.exportdialog.err_tracks" };
    return { what: "tracks", body: { track_ids: chosen }, scope };
  }
  return { what: "mix", body: {}, scope: "whole" };
}
