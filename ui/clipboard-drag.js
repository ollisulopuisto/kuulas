// Dragging a clipboard entry from the Clipboard tab onto the timeline (ROADMAP "Drag clips from
// the Clipboard panel onto the timeline"; docs/design/CLIPBOARD-SHELVES.md: from every view).
// Where a drop lands and the outlines drawn while dragging are pure; the controller keeps the
// dragged entry (a drag's data cannot be read until the drop) and on the drop adopts an entry
// of another shelf into this project first, then pastes it as one edit, as Mod+V would at that
// frame and track. The paste links missing recordings in place, hash-checked (rule 17).
import { pasteChoice, pasteTargets } from "./clipboard.js";
import { frameToX, xToFrame } from "./format.js";
import { RULER_HEIGHT, rowAt } from "./lanes.js";
import { moveTargets, snapMove } from "./move-snap.js";

/** The drag data type of a clipboard entry; its value is the entry id. */
export const CLIP_DRAG_TYPE = "application/x-kuulas-clipboard";

export function isClipboardDrag(dataTransfer) {
  return [...(dataTransfer?.types ?? [])].includes(CLIP_DRAG_TYPE);
}

/** The entry's length in frames (its span; the API's `length`). */
const lengthOf = (entry) => Math.max(0, Number(entry?.length) || 0);

/**
 * What a drop at pixel (x, y) of the timeline canvas would do: { trackId, at, snapAt,
 * targetTracks } or null (the ruler, a gap, a bus, the empty space below the tracks). The pointer
 * holds the entry by its start. As when moving clips, the entry's start and end snap to other
 * clips' edges, the playhead and the marks within 8 px; Alt turns snapping off and, when the
 * start would fall inside a clip of the track, stops it at that clip's end (the neighbour), so
 * an Alt drop never begins on top of material. The slots go on the track and the ones below it,
 * as "paste on the current track" does. `view` is { scroll, zoom, scrollY }.
 */
export function dropTarget({ x, y, alt = false }, { layout, project, view, entry, marks = {} }) {
  if (!project || !entry || y < RULER_HEIGHT) return null;
  const row = rowAt(layout, y - RULER_HEIGHT + view.scrollY);
  if (row?.kind !== "track") return null;
  const track = project.tracks.find((item) => item.id === row.id);
  if (!track) return null;
  let at = Math.max(0, xToFrame(x, view.scroll, view.zoom));
  let snapAt = null;
  if (alt) {
    const under = (track.clips ?? []).find(
      (clip) => clip.start < at && at < clip.start + clip.length,
    );
    if (under) at = under.start + under.length;
  } else {
    const snapped = snapMove({
      moved: [{ start: 0, end: lengthOf(entry) }],
      delta: at,
      targets: moveTargets(project, [], marks),
      zoom: view.zoom,
    });
    at = snapped.delta;
    snapAt = snapped.at;
  }
  const ids = project.tracks.map((item) => item.id);
  const slots = Math.max(1, Number(entry.slots) || 1);
  return {
    trackId: track.id,
    at: Math.max(0, Math.round(at)),
    snapAt,
    targetTracks: pasteTargets(slots, ids, track.id),
  };
}

/**
 * The outlines drawn while dragging, in canvas pixels: one per clip of the entry at its place
 * in the layout and on the track its slot goes to (`outlines`), and the target track's band
 * (`rows`) to highlight. An entry without references is one outline of its length.
 */
export function dropOutlines(entry, target, { layout, view }) {
  const rowOf = (id) => layout.rows.find((row) => row.kind === "track" && row.id === id);
  const top = (row) => RULER_HEIGHT + row.top - view.scrollY;
  const refs = entry.refs?.length
    ? entry.refs
    : [{ rel_start: 0, length: lengthOf(entry), track_slot: 0 }];
  const outlines = [];
  for (const ref of refs) {
    const row = rowOf(target.targetTracks?.[ref.track_slot] ?? target.trackId);
    if (!row) continue;
    outlines.push({
      x: frameToX(target.at + ref.rel_start, view.scroll, view.zoom),
      y: top(row),
      w: ref.length / view.zoom,
      h: row.height,
    });
  }
  const anchor = rowOf(target.trackId);
  return { outlines, rows: anchor ? [{ y: top(anchor), h: anchor.height }] : [] };
}

/**
 * The drag in the app. `timeline`: clipboardDropTarget(event, entry) and
 * setClipboardDropPreview({ target, entry } | null); `adopt(entry, source)` -> the adopted
 * entry or null; `paste(args, entry)` sends the paste. `source` is { shelf, from }: shelf
 * "project" (this project's own: pasted as it is), "series", "shared" or "other".
 */
export function createClipboardDrag({ getState, timeline, adopt, paste }) {
  let dragged = null; // { entry, source }

  const clear = () => {
    dragged = null;
    timeline.setClipboardDropPreview(null);
  };

  return {
    active: () => dragged !== null,
    start(entry, source) {
      dragged = { entry, source: source ?? { shelf: "project", from: "" } };
    },
    /** dragover: true (and the drop allowed) when it is over a place to drop. */
    over(event) {
      if (!dragged || !isClipboardDrag(event.dataTransfer)) return false;
      const target = timeline.clipboardDropTarget(event, dragged.entry);
      timeline.setClipboardDropPreview(target ? { target, entry: dragged.entry } : null);
      if (!target) return false;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      return true;
    },
    /** The drop: one paste edit, after adopting an entry that is not this project's. */
    async drop(event) {
      if (!dragged) return false;
      const { entry, source } = dragged;
      const target = timeline.clipboardDropTarget(event, entry);
      clear();
      if (!target) return false;
      event.preventDefault?.();
      let id = entry.id;
      if (source.shelf !== "project") {
        const mine = await adopt(entry, source);
        if (!mine) return false;
        id = mine.id;
      }
      paste(
        {
          entry_id: id,
          at: target.at,
          mode: pasteChoice(getState()).mode,
          target_tracks: target.targetTracks,
        },
        entry,
      );
      return true;
    },
    /** dragend (also Esc, or a drop somewhere else): nothing is pasted. */
    end: clear,
  };
}
