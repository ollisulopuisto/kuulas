// Track kind (speech / music) and speaker, the WP22 tags. Pure; the header tag
// and the inspector field live in tracks.js and inspector-track.js.

import { currentTrack } from "./selection.js";
import { TRACK_KINDS } from "./track-target.js";

/** The kind Alt+Mod+K gives next: speech, music, back to speech. */
export function nextKind(kind) {
  const at = TRACK_KINDS.indexOf(kind);
  return TRACK_KINDS[(at + 1) % TRACK_KINDS.length];
}

/** Alt+Mod+K: one `set_track` edit (one undo step) for the focused track, with a toast. */
export function cycleKindPlan(state) {
  if (!state?.project) return null;
  const id = currentTrack(state);
  const track = id === null ? null : state.project.tracks.find((item) => item.id === id);
  if (!track) return null;
  const kind = nextKind(track.kind);
  return {
    op: "set_track",
    args: { track_id: track.id, kind },
    label: { key: "ui.edit.label.track_kind" },
    toast: { key: `ui.edit.toast.track_kind.${kind}`, values: { name: track.name } },
  };
}

/** Whose microphone a track is: its speaker, else its own name (as the model does). */
export const speakerKey = (track) => track.speaker?.trim() || track.name;

/** The other speech tracks that are one analysis lane with this one (same speaker). */
export function laneMates(project, trackId) {
  const track = project.tracks.find((item) => item.id === trackId);
  if (!track || track.kind === "music") return [];
  const key = speakerKey(track);
  return project.tracks.filter(
    (item) => item.id !== trackId && item.kind !== "music" && speakerKey(item) === key,
  );
}

/** The `set_track` args for text typed in the Speaker field; blank or the own name is "". */
export function speakerArgs(track, text) {
  const value = text.trim();
  return { track_id: track.id, speaker: value === track.name ? "" : value };
}
