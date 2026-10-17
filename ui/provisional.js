// Provisional results: what the screen shows the moment a control moves,
// before the server has answered (ground rule 14). Pure and immutable; the
// server's answer replaces the project once the queue is empty.

/** The coalesce key of a control: one drag becomes one undo step. */
export const coalesceKey = (kind, field, id) => `${kind}-${field}-${id}`;

const clampPan = (fields) =>
  "pan" in fields ? { ...fields, pan: Math.max(-1, Math.min(1, Number(fields.pan))) } : fields;

export function patchTrack(project, trackId, fields) {
  if (!project.tracks.some((track) => track.id === trackId)) return project;
  const patch = clampPan(fields);
  return {
    ...project,
    tracks: project.tracks.map((track) => (track.id === trackId ? { ...track, ...patch } : track)),
  };
}

export function patchBus(project, busId, fields) {
  if (!project.buses.some((bus) => bus.id === busId)) return project;
  const patch = clampPan(fields);
  return {
    ...project,
    buses: project.buses.map((bus) => (bus.id === busId ? { ...bus, ...patch } : bus)),
  };
}

export function patchClip(project, clipId, fields) {
  if (!project.tracks.some((track) => track.clips.some((clip) => clip.id === clipId)))
    return project;
  const patch = clampPan(fields);
  return {
    ...project,
    tracks: project.tracks.map((track) =>
      track.clips.some((clip) => clip.id === clipId)
        ? {
            ...track,
            clips: track.clips.map((clip) => (clip.id === clipId ? { ...clip, ...patch } : clip)),
          }
        : track,
    ),
  };
}

/** The `solo` edit's rule: exclusive clears the others (and clicking the only one clears it). */
export function patchSolo(project, trackId, exclusive) {
  const soloed = new Set(project.tracks.filter((track) => track.solo).map((track) => track.id));
  let target;
  if (exclusive) target = soloed.size === 1 && soloed.has(trackId) ? new Set() : new Set([trackId]);
  else {
    target = new Set(soloed);
    if (!target.delete(trackId)) target.add(trackId);
  }
  return {
    ...project,
    tracks: project.tracks.map((track) =>
      target.has(track.id) === track.solo ? track : { ...track, solo: target.has(track.id) },
    ),
  };
}
