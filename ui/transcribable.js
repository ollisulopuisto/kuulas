// Which recordings are worth transcribing (pure; the same rule as src/kuulas/transcribable.py).
// A recording is skipped when EVERY clip that uses it is on a music-kind track: one on a speech
// track too is still transcribed, one used nowhere is transcribed as before.

/** Ids of the recordings with at least one clip, all of them on music tracks (a Set). */
export function musicOnlyIds(project) {
  const onMusic = new Set();
  const elsewhere = new Set();
  for (const track of project?.tracks ?? []) {
    const target = track.kind === "music" ? onMusic : elsewhere;
    for (const clip of track.clips) target.add(clip.media);
  }
  for (const id of elsewhere) onMusic.delete(id);
  return onMusic;
}

/** Is this recording to be transcribed? */
export const isTranscribable = (project, mediaId) => !musicOnlyIds(project).has(mediaId);

/** `ids` without the music-only recordings. */
export function withoutMusic(project, ids) {
  const music = musicOnlyIds(project);
  return ids.filter((id) => !music.has(id));
}

/**
 * The transcript panel's note: the selected clip's recording when it is music-only and has no
 * words (a music recording that already has a transcript just shows it). -> { id, name } | null.
 */
export function musicNote({ project, selection, transcribed }) {
  if (!project || !selection || selection.size !== 1) return null;
  const [clipId] = selection;
  for (const track of project.tracks) {
    const clip = track.clips.find((item) => item.id === clipId);
    if (!clip) continue;
    if (!musicOnlyIds(project).has(clip.media) || transcribed.includes(clip.media)) return null;
    const media = project.media.find((item) => item.id === clip.media);
    return { id: clip.media, name: media?.name ?? clip.media };
  }
  return null;
}
