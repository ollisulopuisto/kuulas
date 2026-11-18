/** How far the collapsed track header (drag strip + name pill) reaches into a
 * lane, per track, in px. tracks.js measures it; the timeline painter starts
 * clip labels right of it so the overlay never covers a clip's name. */
const insets = new Map();

export function setLaneInset(trackId, px) {
  insets.set(trackId, px);
}

export function laneInset(trackId) {
  return insets.get(trackId) ?? 0;
}
