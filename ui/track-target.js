// What the inspector's Track/Bus section shows for the current row. Pure; the
// DOM lives in inspector-track.js.

import { busLetter } from "./grammar.js";

/** Tracks on a bus. */
export const busMembers = (project, busId) =>
  project.tracks.filter((track) => track.bus === busId).length;

/** The locale key naming a track's role (speech, speech mix, music). */
export const roleKey = (kind) => `ui.track.kind.${kind}`;

/** "No bus" first, then every bus (an empty one too) with its badge letter. */
export function busOptions(project) {
  return [
    { value: "", letter: "", name: "" },
    ...project.buses.map((bus, i) => ({ value: bus.id, letter: busLetter(i), name: bus.name })),
  ];
}

function busInfo(project, busId) {
  const index = project.buses.findIndex((bus) => bus.id === busId);
  if (index < 0) return null;
  return {
    bus: project.buses[index],
    letter: busLetter(index),
    members: busMembers(project, busId),
  };
}

/**
 * Which track or bus the inspector describes. A current bus row wins; else the
 * current track (up/down cursor), else the track of the one selected clip.
 * A track alone on its bus is merged into its header, so its bus is offered
 * too (`merged`, `trackBus`).
 */
export function inspectorTarget(state) {
  const none = { track: null, bus: null };
  const project = state.project;
  if (!project) return none;
  if (state.focusBus) {
    const bus = busInfo(project, state.focusBus);
    return bus ? { track: null, bus } : none;
  }
  let track = project.tracks.find((item) => item.id === state.focusTrack);
  if (!track && state.selection?.size === 1) {
    const [clipId] = state.selection;
    track = project.tracks.find((item) => item.clips.some((clip) => clip.id === clipId));
  }
  if (!track) return none;
  const trackBus = track.bus ? busInfo(project, track.bus) : null;
  return { track, bus: null, trackBus, merged: Boolean(trackBus) && trackBus.members === 1 };
}
