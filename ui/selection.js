// What the selection, the in/out range and the current track mean for an editing
// command. Pure functions of the store's state, so the commands' `can()` and the
// edits they send agree, and node tests cover them.
import { clipEnd } from "./lanes.js";

const tracksOf = (state) => state?.project?.tracks ?? [];

/** [{ clip, trackId }] for the selected clips, in track order. */
export function selectedClips(state) {
  const selection = state?.selection;
  if (!selection || selection.size === 0) return [];
  return tracksOf(state).flatMap((track) =>
    track.clips
      .filter((clip) => selection.has(clip.id))
      .map((clip) => ({ clip, trackId: track.id })),
  );
}

/** The in/out range as { start, end } (in frames, in order), or null unless both are set and differ. */
export function markedRange(state) {
  const { inPoint, outPoint } = state ?? {};
  if (inPoint == null || outPoint == null || inPoint === outPoint) return null;
  return { start: Math.min(inPoint, outPoint), end: Math.max(inPoint, outPoint) };
}

/**
 * The track a command acts on when it acts on "this track": the focused one, else
 * the one track all selected clips sit on. A focused bus row has no current track.
 */
export function currentTrack(state) {
  if (state?.focusBus) return null;
  const tracks = tracksOf(state);
  if (state?.focusTrack)
    return tracks.some((t) => t.id === state.focusTrack) ? state.focusTrack : null;
  const onTracks = new Set(selectedClips(state).map((entry) => entry.trackId));
  return onTracks.size === 1 ? [...onTracks][0] : null;
}

/** Ids of the clips the frame lies strictly inside, on one track or (null) all. */
export function clipsAround(project, frame, trackId = null) {
  return (project?.tracks ?? [])
    .filter((track) => trackId === null || track.id === trackId)
    .flatMap((track) =>
      track.clips.filter((clip) => clip.start < frame && frame < clipEnd(clip)).map((c) => c.id),
    );
}

/** Mod+A (this track) and Alt+Mod+A (all tracks): the clip ids to select. */
export function selectAllIds(state, allTracks) {
  const track = allTracks ? null : currentTrack(state);
  if (!allTracks && track === null) return [];
  return tracksOf(state)
    .filter((t) => allTracks || t.id === track)
    .flatMap((t) => t.clips.map((c) => c.id));
}
