// Timing-review state is separate from the edit. Frame offsets stay integers.
export function selectedTrackIds(state) {
  const tracks = state.project?.tracks ?? [];
  const headers = state.trackSelection ?? new Set();
  const clips = state.selection ?? new Set();
  const selected = tracks.filter(
    (track) => headers.has(track.id) || track.clips.some((clip) => clips.has(clip.id)),
  );
  return (selected.length ? selected : tracks)
    .filter((track) => track.clips.length)
    .map((track) => track.id);
}

/**
 * The pieces a review is limited to, or null for the whole tracks. When the selected pieces leave
 * other pieces of the same tracks out (two sets of files recorded separately), only the selected
 * ones are measured and moved; a track chosen without any selected piece, or a selection that covers
 * every piece, means the whole tracks, as before.
 */
export function selectedClipIds(state) {
  const ids = new Set(selectedTrackIds(state));
  const chosen = (state.project?.tracks ?? []).filter((track) => ids.has(track.id));
  const picked = new Set(state.selection ?? []);
  const lists = chosen.map((track) => track.clips.filter((clip) => picked.has(clip.id)));
  if (lists.some((list) => list.length === 0)) return null;
  if (lists.every((list, i) => list.length === chosen[i].clips.length)) return null;
  return lists.flat().map((clip) => clip.id);
}

export function moveRequest(review, track, clip, delta, scope) {
  return {
    id: review.id,
    track,
    frames: scope === "clip" ? (review.offsets[clip] ?? 0) + delta : delta,
    clip: scope === "clip" ? clip : null,
  };
}

export function auditionRange(frame, length, rate) {
  const at = Math.max(0, frame - 3 * rate);
  return { at, seconds: Math.max(0.1, Math.min(6, (length - at) / rate)) };
}

/** Keep the method attribution, but do not call an adjusted proposal automatic. */
export function timingStatus(review, track, row) {
  return track.clips.some((clip) => review.offsets[clip.id] !== review.suggestion[clip.id])
    ? "manual"
    : (row?.status ?? "manual");
}
