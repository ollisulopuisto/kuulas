// The "(options)…" export dialog (WP74): File > Export mix (options)… and Export all tracks
// (options)… ask for the format, and whether to choose the folder first. The per-format
// commands (export.mix_<f>, export.tracks_<f>) stay in the palette; this dialog covers them all.

import { ALWAYS_AVAILABLE } from "./export-commands.js";

const FALLBACK = { wav: "WAV", flac: "FLAC" };

/**
 * The formats the dialog lists: the server's ([{ id, label }], its order), or WAV and FLAC (which
 * need no codec) while the server has not answered.
 */
export function dialogFormats(offered) {
  if (Array.isArray(offered) && offered.length > 0) return offered;
  return ALWAYS_AVAILABLE.map((id) => ({ id, label: FALLBACK[id] ?? id }));
}

/** The format to preselect: the remembered one when it is listed, else the first (WAV). */
export function pickFormat(formats, remembered) {
  if (formats.some((format) => format.id === remembered)) return remembered;
  return formats[0]?.id ?? "wav";
}

/** What the dialog hands back: `what` is "mix" or "tracks". */
export function exportDialogRequest(what, { format, ask }) {
  if (what !== "mix" && what !== "tracks") throw new Error(`unknown export kind: ${what}`);
  return { what, format, ask: Boolean(ask) };
}
