// Collapsing buses: which bus a command acts on, and the next set of collapsed buses.
// Pure, so the commands' `can()` and what they do agree (null = nothing would change).
// The set is view state, remembered with the view (view-memory.js), never in the history.

const busesOf = (project) => project?.buses ?? [];
const tracksOf = (project) => project?.tracks ?? [];

/** The bus in focus: the focused bus, else the bus of the focused track, else null. */
export function busOfFocus(state) {
  if (state?.focusBus) return state.focusBus;
  const track = tracksOf(state?.project).find((item) => item.id === state?.focusTrack);
  return track?.bus ?? null;
}

/**
 * Buses that have a row to fold: two or more tracks. A one-track bus is merged into
 * its track's header (GUI-DESIGN section 6) and an empty one has nothing to hide.
 */
export function collapsibleBuses(project) {
  const count = new Map();
  for (const track of tracksOf(project)) count.set(track.bus, (count.get(track.bus) ?? 0) + 1);
  return busesOf(project)
    .filter((bus) => (count.get(bus.id) ?? 0) >= 2)
    .map((bus) => bus.id);
}

const current = (state) => state?.collapsedBuses ?? new Set();

/** The set after collapsing or expanding the bus in focus; null when nothing would change. */
export function collapseChange(state, collapse) {
  const id = busOfFocus(state);
  if (id === null || !collapsibleBuses(state.project).includes(id)) return null;
  const set = current(state);
  if (set.has(id) === collapse) return null;
  const next = new Set(set);
  if (collapse) next.add(id);
  else next.delete(id);
  return next;
}

/** The set after collapsing every collapsible bus, or expanding all; null when no change. */
export function collapseAllChange(state, collapse) {
  const set = current(state);
  const all = collapsibleBuses(state?.project);
  if (collapse) {
    if (all.every((id) => set.has(id))) return null;
    return new Set([...set, ...all]);
  }
  if (set.size === 0) return null;
  return new Set();
}

/** The chevron and the double-click: flip one bus. */
export function toggleChange(state, id) {
  const next = new Set(current(state));
  if (!next.delete(id)) next.add(id);
  return next;
}

/** Shift+click on a collapsed bus row: the ids of the member clips that hold `frame`. */
export function memberClipsAt(project, busId, frame) {
  return tracksOf(project)
    .filter((track) => track.bus === busId)
    .flatMap((track) => track.clips ?? [])
    .filter((clip) => clip.start <= frame && frame < clip.start + clip.length)
    .map((clip) => clip.id);
}
