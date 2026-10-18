// The Select commands (WP54): the selection and the in/out range made from one another.
// UI state only (no edit, no undo step); the arithmetic is in selection-ops.js.
// "Which tracks" is the same answer an edit would use (edit-plans.js rangeTracks):
// the range's chosen tracks, else this track, else the selected clips' tracks; with
// none of those, every track.
import { expandGroups } from "./clip-groups.js";
import { rangeTracks } from "./edit-plans.js";
import { markedRange, selectedClips } from "./selection.js";
import {
  clipsInRange,
  forwardFromClips,
  forwardFromFrame,
  invert,
  rangeFromClips,
} from "./selection-ops.js";

export const SELECT_COMMANDS = [
  "select.range_all_tracks",
  "select.clips_in_range",
  "select.range_from_clips",
  "select.forward",
  "select.forward_from_clips",
  "select.forward_all_tracks_from_clips",
  "select.invert",
  "select.none",
];

const scope = (state) => {
  const tracks = rangeTracks(state);
  return tracks.length > 0 ? tracks : null;
};

/** `app`: getState, patch(statePatch). */
export function registerSelectCommands(registry, { app }) {
  const def = (id, run, can) => registry.register(id, run, { can, hintKey: `cmd.${id}.hint` });
  const hasProject = (state) => Boolean(state?.project);
  const selection = (state) => state?.selection ?? new Set();

  // What each command would select, or null when it does not apply: the command runs
  // it and `can()` asks it, so the two cannot disagree.
  const chooser = {
    "select.clips_in_range": (state) => {
      const range = markedRange(state);
      return range ? clipsInRange(state.project, range, scope(state)) : null;
    },
    "select.forward": (state) =>
      hasProject(state) && Number.isFinite(state.playhead)
        ? forwardFromFrame(state.project, state.playhead, scope(state))
        : null,
    "select.forward_from_clips": (state) => forwardFromClips(state?.project, selection(state)),
    "select.forward_all_tracks_from_clips": (state) =>
      forwardFromClips(state?.project, selection(state), { allTracks: true }),
    "select.invert": (state) =>
      hasProject(state) ? invert(state.project, selection(state), scope(state)) : null,
  };
  for (const [id, choose] of Object.entries(chooser)) {
    def(
      id,
      () => {
        const state = app.getState();
        app.patch({ selection: expandGroups(state.project, choose(state)) });
      },
      (state) => (choose(state)?.size ?? 0) > 0,
    );
  }

  def(
    "select.range_all_tracks",
    () =>
      app.patch({ rangeTracks: new Set(app.getState().project.tracks.map((track) => track.id)) }),
    (state) => hasProject(state) && state.project.tracks.length > 0 && markedRange(state) !== null,
  );
  def(
    "select.range_from_clips",
    () => {
      const state = app.getState();
      const span = rangeFromClips(state.project, selection(state));
      const tracks = [...new Set(selectedClips(state).map((entry) => entry.trackId))];
      app.patch({ inPoint: span.start, outPoint: span.end, rangeTracks: new Set(tracks) });
    },
    (state) => rangeFromClips(state?.project, selection(state)) !== null,
  );
  def(
    "select.none",
    () => app.patch({ selection: new Set(), rangeTracks: new Set() }),
    (state) => selection(state).size > 0 || (state?.rangeTracks?.size ?? 0) > 0,
  );
}
