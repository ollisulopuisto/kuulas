/** Toggle every bus member in the existing track solo set, without new bus state. */
export function busSoloTarget(tracks, busId, additive = false) {
  const members = tracks.filter((track) => track.bus === busId);
  const current = tracks.filter((track) => track.solo).map((track) => track.id);
  if (!members.length) return current;
  const ids = members.map((track) => track.id);
  const all = members.every((track) => track.solo);
  if (additive) {
    const target = new Set(current);
    for (const id of ids) all ? target.delete(id) : target.add(id);
    return tracks.filter((track) => target.has(track.id)).map((track) => track.id);
  }
  return all && current.length === ids.length ? [] : ids;
}

/** The same member edits for a header button, shortcut, menu or palette. */
export function busSoloEdits(state, busId, additive = false) {
  const tracks = state?.project?.tracks ?? [];
  if (!state?.project?.buses?.some((bus) => bus.id === busId)) return [];
  const target = new Set(busSoloTarget(tracks, busId, additive));
  return tracks
    .filter((track) => Boolean(track.solo) !== target.has(track.id))
    .map((track) => ({ op: "solo", args: { track_id: track.id, exclusive: false } }));
}
