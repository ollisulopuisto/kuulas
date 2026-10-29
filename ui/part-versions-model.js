import { currentTrack, markedRange, selectedClips } from "./selection.js";

/** A single track and frame range; never guess which of several lanes to restore. */
export function partRange(state) {
  const track = currentTrack(state);
  const marked = markedRange(state);
  if (track && marked) return { track_id: track, ...marked };
  const selected = selectedClips(state);
  if (!selected.length || new Set(selected.map((entry) => entry.trackId)).size !== 1) return null;
  return {
    track_id: selected[0].trackId,
    start: Math.min(...selected.map(({ clip }) => clip.start)),
    end: Math.max(...selected.map(({ clip }) => clip.start + clip.length)),
  };
}
