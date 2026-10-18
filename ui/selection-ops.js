// Selection arithmetic (WP54): which clips a range, a frame or a selection implies, and
// the other way round. Pure (project in, Set of clip ids out) so `node --test` covers it.
// Muted clips are clips like any other and are included. `tracks` is a list of track
// ids, or null/undefined for every track; an empty list means no track.
import { selectionSpan } from "./view.js";

const end = (clip) => clip.start + clip.length;

function tracksIn(project, tracks) {
  const all = project?.tracks ?? [];
  if (tracks == null) return all;
  const wanted = new Set(tracks);
  return all.filter((track) => wanted.has(track.id));
}

/** The clips that overlap [start, end) on the given tracks (touching edges do not count). */
export function clipsInRange(project, range, tracks = null) {
  const found = new Set();
  if (!range) return found;
  for (const track of tracksIn(project, tracks)) {
    for (const clip of track.clips ?? []) {
      if (clip.start < range.end && end(clip) > range.start) found.add(clip.id);
    }
  }
  return found;
}

/** First start to last end of the selected clips, or null (the same span Shift+Z fits). */
export function rangeFromClips(project, selection) {
  return selectionSpan(project, selection);
}

/** Every clip whose end is after `frame`: the one holding it and all later ones. */
export function forwardFromFrame(project, frame, tracks = null) {
  const found = new Set();
  for (const track of tracksIn(project, tracks)) {
    for (const clip of track.clips ?? []) if (end(clip) > frame) found.add(clip.id);
  }
  return found;
}

/**
 * Per track holding a selected clip: its earliest selected clip and every clip after it.
 * With `allTracks`: the selected clips and every clip on every track that starts at or after the
 * earliest selected start (a long clip that began earlier, such as a music bed, is not swept in).
 */
export function forwardFromClips(project, selection, { allTracks = false } = {}) {
  const found = new Set();
  if (!selection || selection.size === 0) return found;
  const all = project?.tracks ?? [];
  if (allTracks) {
    const span = selectionSpan(project, selection);
    if (!span) return found;
    for (const track of all) {
      for (const clip of track.clips ?? []) {
        if (clip.start >= span.start || selection.has(clip.id)) found.add(clip.id);
      }
    }
    return found;
  }
  for (const track of all) {
    const starts = (track.clips ?? []).filter((c) => selection.has(c.id)).map((c) => c.start);
    if (starts.length === 0) continue;
    const from = Math.min(...starts);
    for (const clip of track.clips) if (clip.start >= from) found.add(clip.id);
  }
  return found;
}

/**
 * Cmd+Alt+click (Hindenburg's way): the clicked clip and every clip on every track that
 * starts at or after it.
 */
export function forwardFromClip(project, clipId) {
  const known = (project?.tracks ?? []).some((track) =>
    (track.clips ?? []).some((clip) => clip.id === clipId),
  );
  return known ? forwardFromClips(project, new Set([clipId]), { allTracks: true }) : new Set();
}

/** The clips on the given tracks that are not selected. */
export function invert(project, selection, tracks = null) {
  const found = new Set();
  for (const track of tracksIn(project, tracks)) {
    for (const clip of track.clips ?? []) if (!selection?.has(clip.id)) found.add(clip.id);
  }
  return found;
}
