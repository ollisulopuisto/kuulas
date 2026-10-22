// Every export honours the selection (owner, 2026-10-21). What a selection means for an
// export, as pure functions; app.js, the export dialogs and the automixer dialog use them.
//
//   1. In/Out marks (or a mouse-painted range): that time range, on the tracks the range
//      scope resolves (range-scope.js: all by default, the painted lanes, or the selected
//      tracks) - the same tracks Backspace and X act on.
//   2. Else selected clips: the tracks that hold them, over their combined time span.
//      Everything on those tracks inside the span counts, not only the selected clips.
//   3. Else nothing: the whole mix, as before.
//
// Mute and solo are not applied here: the export itself applies them as for the whole mix.
import { hasRange } from "./export-dialog-model.js";
import { resolveScope } from "./range-scope.js";

/**
 * -> null (no selection) or { source: "marks" | "clips", range: [start, end] frames,
 * trackIds: ids in project order, or null for all tracks, names: those tracks' names ([]
 * for all) }. `length` is the mix length in frames: the range is cut there, and a span that
 * is the whole mix on all tracks is no selection at all.
 */
export function resolveExportSelection(state, { length }) {
  const tracks = state?.project?.tracks ?? [];
  const every = (ids) => ids.length === 0 || ids.length >= tracks.length;
  const finish = (source, from, to, ids) => {
    const range = [Math.max(0, from), Math.min(length, to)];
    if (!(range[1] > range[0])) return null;
    const all = every(ids);
    if (all && range[0] === 0 && range[1] >= length) return null;
    const chosen = tracks.filter((track) => ids.includes(track.id));
    return {
      source,
      range,
      trackIds: all ? null : chosen.map((track) => track.id),
      names: all ? [] : chosen.map((track) => track.name),
    };
  };
  if (hasRange(state)) {
    const scope = resolveScope(state);
    // Selected-tracks mode with no track selected would touch nothing: export all tracks.
    return finish("marks", state.inPoint, state.outPoint, scope.none ? [] : scope.tracks);
  }
  const picked = state?.selection ?? new Set();
  if (picked.size === 0) return null;
  let from = Number.POSITIVE_INFINITY;
  let to = Number.NEGATIVE_INFINITY;
  const holding = [];
  for (const track of tracks) {
    let holds = false;
    for (const clip of track.clips ?? []) {
      if (!picked.has(clip.id)) continue;
      holds = true;
      from = Math.min(from, clip.start);
      to = Math.max(to, clip.start + clip.length);
    }
    if (holds) holding.push(track.id);
  }
  if (holding.length === 0) return null;
  return finish("clips", from, to, holding);
}

/** The request fields a selection adds: the range, and the tracks when not all. */
export function selectionBody(selection) {
  if (!selection) return {};
  const body = { range: [...selection.range] };
  if (selection.trackIds) body.track_ids = [...selection.trackIds];
  return body;
}

/** "mm.ss-mm.ss" of a range (whole seconds, minutes not wrapped), as the automixer's names. */
export function spanDots(range, rate) {
  const one = (frame) => {
    const seconds = Math.floor(frame / rate);
    const pad = (n) => String(n).padStart(2, "0");
    return `${pad(Math.floor(seconds / 60))}.${pad(seconds % 60)}`;
  };
  return `${one(range[0])}-${one(range[1])}`;
}

/** "Exporting the selection only: tracks Anna, Ville, 12.00-18.30" ("" without a selection). */
export function selectionNotice(selection, rate, t) {
  if (!selection) return "";
  const span = spanDots(selection.range, rate);
  if (!selection.trackIds) return t("ui.export.selection_only", { span });
  return t("ui.export.selection_only_tracks", { tracks: selection.names.join(", "), span });
}
