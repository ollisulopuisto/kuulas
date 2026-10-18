// Dropping files on the editor: where the drop lands, what to show before
// release, and how a dropped folder becomes a list of audio files.
// Pure (no DOM), so `node --test` covers it. Spec: docs/design/GUI-DESIGN.md §23.
import { frameToTime, frameToX, xToFrame } from "./format.js";
import { RULER_HEIGHT, rowAt } from "./lanes.js";

/** At most this many ghost clips are drawn, however many files are dragged. */
export const MAX_GHOSTS = 8;
const GHOST_W = 96;
const GHOST_H = 28;
const GHOST_STRIDE = 34;
const GHOST_GAP = 4;
const LINE_OFFSET = 2;
const BLOCK_TOP = 8;
const EDGE_MARGIN = 4;

/**
 * What a drop at pixel (x, y) of the timeline canvas will do. Pointer in the
 * ruler: new tracks starting at that time. On a lane: start at the drop time
 * (the backend places new tracks; it has no "put on this lane" yet, so the lane
 * only tells where in time). Anywhere else, including the empty space below
 * the tracks: new tracks at the start. `alt` asks for one after another.
 * `view` is { scroll, zoom, scrollY }.
 */
export function resolveDropTarget({ x, y, alt = false }, { layout, project, view, count = 1 }) {
  const mode = alt ? "sequential" : "side_by_side";
  const fresh = { kind: "new", startFrame: 0, trackId: null, mode, count };
  if (y < 0) return fresh;
  const startFrame = Math.max(0, xToFrame(x, view.scroll, view.zoom));
  if (y < RULER_HEIGHT) return { ...fresh, kind: "ruler", startFrame };
  const row = rowAt(layout, y - RULER_HEIGHT + view.scrollY);
  if (row?.kind === "track" && project.tracks.some((track) => track.id === row.id)) {
    return { ...fresh, kind: "lane", startFrame, trackId: row.id };
  }
  return fresh;
}

/**
 * Where the picker's files go (owner, 2026-10-19): onto the selected track, one after another,
 * whether it was made first or not. { onto_track, start_frame } or null (no usable selection:
 * every file gets a track of its own, as before). They start at the play cursor, or after the
 * track's last clip when the cursor is inside its material, so nothing is overwritten.
 */
export function pickerPlacement(project, trackId, playhead) {
  const track = project?.tracks?.find((item) => item.id === trackId);
  if (!track) return null;
  const end = Math.max(0, ...track.clips.map((clip) => clip.start + clip.length));
  const start = Math.max(0, Math.round(playhead ?? 0));
  return { onto_track: track.id, start_frame: start >= end ? start : end };
}

/** The placement fields of POST /api/import and /api/upload for a drop (null: the picker). */
export function importOptionsFor(target, prefs) {
  const onLane = target?.kind === "lane" && target.trackId;
  return {
    // Dropped on a lane: onto that track, one file after another from the drop time.
    mode: onLane ? "sequential" : (target?.mode ?? "side_by_side"),
    order: prefs.order,
    track_naming: prefs.trackNaming,
    start_frame: target?.startFrame ?? 0,
    ...(onLane ? { onto_track: target.trackId } : {}),
  };
}

/** The label drawn on the preview: a catalog key and its values. */
export function dropLabel(preview) {
  const count = preview.count;
  if (preview.mode === "sequential") return { key: "ui.import.drop_sequence", params: { count } };
  if (preview.kind === "new") return { key: "ui.import.drop_new", params: { count } };
  return { key: "ui.import.drop_at", params: { count, time: frameToTime(preview.startFrame) } };
}

/**
 * Ghost clips and the insertion line for a drop preview, in canvas pixels.
 * { line: {orientation:"horizontal", y} | {orientation:"vertical", x},
 *   ghosts: [{x, y, w, h}], label: {x, y} }.
 */
export function dropGhosts(preview, { layout, view, size }) {
  const shown = Math.min(Math.max(1, preview.count), MAX_GHOSTS);
  const sequence = preview.mode === "sequential";
  const rows = sequence ? 1 : shown;
  const x0 = frameToX(preview.startFrame, view.scroll, view.zoom);
  const below = RULER_HEIGHT + layout.height - view.scrollY;
  const blockHeight = (rows - 1) * GHOST_STRIDE + GHOST_H;
  const top = Math.max(
    RULER_HEIGHT + EDGE_MARGIN,
    Math.min(below + BLOCK_TOP, size.height - blockHeight - EDGE_MARGIN),
  );
  const ghosts = [];
  for (let i = 0; i < shown; i += 1) {
    ghosts.push(
      sequence
        ? { x: x0 + i * (GHOST_W + GHOST_GAP), y: top, w: GHOST_W, h: GHOST_H }
        : { x: x0, y: top + i * GHOST_STRIDE, w: GHOST_W, h: GHOST_H },
    );
  }
  const line =
    preview.kind === "new"
      ? { orientation: "horizontal", y: Math.min(below + LINE_OFFSET, size.height - LINE_OFFSET) }
      : { orientation: "vertical", x: x0 };
  return { line, ghosts, label: { x: ghosts[0].x + 8, y: ghosts[0].y + 6 } };
}

// -- folders ----------------------------------------------------------------

const AUDIO_EXTENSIONS = new Set([
  "wav",
  "bwf",
  "flac",
  "mp3",
  "m4a",
  "aac",
  "ogg",
  "opus",
  "aif",
  "aiff",
  "caf",
  "wma",
  "mp4",
  "mov",
  "mkv",
  "webm",
]);

/** An audio or video file name worth importing from a folder (not a dot-file or a resource fork). */
export function isAudioName(name) {
  const text = String(name);
  if (text.startsWith(".")) return false;
  const dot = text.lastIndexOf(".");
  return dot > 0 && AUDIO_EXTENSIONS.has(text.slice(dot + 1).toLowerCase());
}

const byName = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

const readBatch = (reader) => new Promise((resolve, reject) => reader.readEntries(resolve, reject));
const fileOf = (entry) => new Promise((resolve, reject) => entry.file(resolve, reject));

async function folderEntries(directory) {
  const reader = directory.createReader();
  const all = [];
  // readEntries gives a batch at a time (about 100 in Chrome) until it gives none.
  for (let batch = await readBatch(reader); batch.length > 0; batch = await readBatch(reader)) {
    all.push(...batch);
  }
  return all;
}

async function filesInFolder(directory) {
  const entries = (await folderEntries(directory)).sort((a, b) => byName.compare(a.name, b.name));
  const out = [];
  for (const entry of entries) {
    if (entry.isDirectory) out.push(...(await filesInFolder(entry)));
    else if (entry.isFile && isAudioName(entry.name)) out.push(await fileOf(entry));
  }
  return out;
}

/**
 * The files of a drop. `entries` are the FileSystemEntry objects taken from
 * the drop event (webkitGetAsEntry, which must be called inside the event);
 * a folder gives the audio files inside it, loose files are kept as dropped.
 * With no entries (an old browser) the plain `files` list is returned. A folder
 * that cannot be read costs that folder only.
 */
export async function collectDroppedFiles(entries, files) {
  if (entries.length === 0) return files;
  const out = [];
  for (const entry of entries) {
    try {
      if (entry.isDirectory) out.push(...(await filesInFolder(entry)));
      else if (entry.isFile) out.push(await fileOf(entry));
    } catch {
      // Unreadable: leave it out; the rest of the drop still imports.
    }
  }
  return out;
}
