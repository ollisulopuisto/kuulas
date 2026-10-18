// Stereo speech after an import: turn it into mono, or keep it? Pure decisions;
// the question itself is drawn by import-panel.js, the edits go through set_track.

export const MONO_CHOICES = ["ask", "mono", "stereo"];

/**
 * What to do with the new stereo speech tracks (`stereo`: [{id, name}] from the
 * import answer) given the remembered choice ("ask" | "mono" | "stereo"; anything
 * else asks). action: none | ask | mono.
 */
export function monoDecision(choice, stereo) {
  const tracks = stereo ?? [];
  if (tracks.length === 0 || choice === "stereo") return { action: "none", tracks: [] };
  return { action: choice === "mono" ? "mono" : "ask", tracks };
}

/** One undoable set_track per track; `labelKey` is the history label's catalog key. */
export function monoEdits(tracks) {
  return tracks.map((track) => ({
    op: "set_track",
    args: { track_id: track.id, mono: true },
    labelKey: "ui.edit.label.mono",
  }));
}

/**
 * "mono" | "stereo" for the header of a speech track, null for music. A track is
 * stereo when it is not flagged mono and one of its files has two channels.
 */
export function monoTag(track, project) {
  if (track.kind === "music") return null;
  if (track.mono) return "mono";
  const channels = new Map((project?.media ?? []).map((m) => [m.id, m.channels]));
  const wide = (track.clips ?? []).some((clip) => (channels.get(clip.media) ?? 1) > 1);
  return wide ? "stereo" : "mono";
}
